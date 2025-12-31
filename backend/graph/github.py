import os
import io
import json
import time
import stat
import shutil
import tempfile
import asyncio
import subprocess
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from fastapi.responses import StreamingResponse
import base64
import io

import git
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from openai import AsyncOpenAI

# PDF generation (pip install reportlab)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OPEN_AI_KEY= os.getenv("OPENAI_API_KEY", "")


# ------------ GLOBALS ------------
OPENAI_KEY = OPEN_AI_KEY
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY missing")

llm = AsyncOpenAI(api_key=OPEN_AI_KEY)
executor = ThreadPoolExecutor(max_workers=6)

router = APIRouter(tags=["github-evaluator"])


# ------------ BASIC UTILS ------------
def safe_rmtree(path: str):
    if not os.path.exists(path):
        return
    def rm(func, p, _): os.chmod(p, stat.S_IWRITE); func(p)
    shutil.rmtree(path, onerror=rm)


def run_shell(cmd: list, timeout=30) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout or ""
    except:
        return ""


def clone_repo(url: str) -> str:
    repo_path = tempfile.mkdtemp(prefix="repo_")
    safe_rmtree(repo_path)
    git.Repo.clone_from(url, repo_path)
    return repo_path


# ------------ REPO SCAN ------------
def get_code_chunks(repo: str) -> List[str]:
    exts = [".py", ".js", ".ts", ".html", ".css", ".cpp", ".java"]
    chunks = []

    for root, _, files in os.walk(repo):
        if ".git" in root:
            continue
        for file in files:
            if not any(file.endswith(x) for x in exts):
                continue
            full = os.path.join(root, file)
            try:
                text = open(full, encoding="utf-8", errors="ignore").read()
            except:
                continue

            parts = text.splitlines()
            for i in range(0, len(parts), 300):
                chunks.append(f"# FILE: {file}\n" + "\n".join(parts[i:i+300]))

    return chunks[:8]


def analyze_structure(repo: str) -> Dict:
    out = {
        "has_readme": False,
        "has_requirements": False,
        "has_tests": False,
        "has_dockerfile": False,
        "has_github_actions": False,
        "file_count": 0,
        "dir_count": 0,
    }

    for root, dirs, files in os.walk(repo):
        out["dir_count"] += len(dirs)
        out["file_count"] += len(files)

        for file in files:
            name = file.lower()
            if name.startswith("readme"):
                out["has_readme"] = True
            if name in ("requirements.txt", "pyproject.toml", "setup.py"):
                out["has_requirements"] = True
            if name == "dockerfile":
                out["has_dockerfile"] = True
            if "tests" in root.lower():
                out["has_tests"] = True
            if ".github/workflows" in root.replace("\\", "/"):
                out["has_github_actions"] = True

    return out


def static_analysis(repo: str):
    radon_raw = run_shell(["radon", "cc", repo, "-s", "-j"], timeout=15)
    pylint_score = 0.0

    try:
        out = run_shell(["pylint", repo, "--score=y"], timeout=25)
        if "rated at" in out:
            pylint_score = float(out.split("rated at ")[1].split("/")[0])
    except:
        pass

    return radon_raw, pylint_score


def plagiarism_score(repo: str) -> float:
    out = run_shell(["npx", "jscpd", repo, "--reporters", "json"], timeout=25)
    try:
        return json.loads(out)["statistics"]["total"]["percentage"]
    except:
        return 0.0


# ------------ CODE SMELL DETECTION ------------
def detect_code_smells(radon_raw: str, pylint_score: float, plag: float, structure: Dict) -> Dict[str, Any]:
    smells = []

    high_complexity_funcs = []
    try:
        data = json.loads(radon_raw) if radon_raw else {}
        for file, items in data.items():
            for fn in items:
                comp = fn.get("complexity", 0)
                if comp >= 10:
                    high_complexity_funcs.append(
                        {"file": file, "name": fn.get("name"), "complexity": comp}
                    )
    except:
        pass

    if high_complexity_funcs:
        smells.append({
            "type": "high_complexity",
            "severity": "high",
            "details": high_complexity_funcs[:20],
            "message": "Some functions have very high cyclomatic complexity (>=10)."
        })

    if not structure.get("has_tests"):
        smells.append({
            "type": "missing_tests",
            "severity": "high",
            "message": "No tests folder or test files detected."
        })

    if pylint_score < 5.0:
        smells.append({
            "type": "low_pylint",
            "severity": "medium",
            "message": f"Pylint score is low ({pylint_score}/10)."
        })

    if plag >= 25.0:
        smells.append({
            "type": "duplication",
            "severity": "medium",
            "message": f"High code duplication detected: {plag:.2f}%."
        })

    if not structure.get("has_readme"):
        smells.append({
            "type": "missing_readme",
            "severity": "low",
            "message": "README not found or not named correctly."
        })

    if not structure.get("has_requirements"):
        smells.append({
            "type": "missing_dependencies",
            "severity": "low",
            "message": "No dependency file (requirements.txt/pyproject/ setup) found."
        })

    return {
        "smell_count": len(smells),
        "smells": smells
    }


def compute_risk_score(plag: float, pylint_score: float, code_smells: Dict[str, Any], structure: Dict) -> float:
    smell_count = code_smells.get("smell_count", 0)
    base = 0.0

    base += plag * 0.4
    base += max(0.0, (10.0 - pylint_score)) * 3.0
    base += smell_count * 4.0
    if not structure.get("has_tests"):
        base += 15.0
    if not structure.get("has_readme"):
        base += 5.0

    return round(max(0.0, min(100.0, base)), 2)


# ------------ LLM EVAL ------------
async def llm_code_rating(desc: str, chunks: List[str]):
    logic, relevance, style = [], [], []
    feedback = []

    for c in chunks:
        prompt = {
            "role": "user",
            "content": (
                "Rate this code strictly. Return JSON only:\n"
                '{"logic":80,"relevance":85,"style":75,"feedback":"..."}\n\n'
                f"PROJECT: {desc}\nCODE:\n{c}"
            )
        }

        res = await llm.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[prompt],
            response_format={"type": "json_object"}
        )

        data = json.loads(res.choices[0].message.content)

        logic.append(data.get("logic", 70))
        relevance.append(data.get("relevance", 70))
        style.append(data.get("style", 70))
        feedback.append(data.get("feedback", ""))

    return sum(logic)/len(logic), sum(relevance)/len(relevance), sum(style)/len(style), feedback


# ------------ MARKDOWN MENTOR ------------
async def generate_markdown_mentor(desc: str, result: dict) -> str:
    system = (
        "You are a senior software architect.\n"
        "Return STRICT MARKDOWN in this structure:\n\n"
        "# <Project Title> – Code Review Analysis\n\n"
        "## Code Logic\n"
        "###  Problems\n"
        "- ...\n\n"
        "###  How to Fix\n"
        "- ...\n\n"
        "---\n\n"
        "## Code Quality\n"
        "###  Problems\n"
        "- ...\n\n"
        "###  How to Fix\n"
        "- ...\n\n"
        "---\n\n"
        "## Structure\n"
        "### Problems\n"
        "- ...\n\n"
        "###  How to Fix\n"
        "- ...\n\n"
        "---\n\n"
        "## Plagiarism\n"
        "###  Problems\n"
        "- ...\n\n"
        "###  How to Fix\n"
        "- ...\n\n"
        "---\n\n"
        "## Risk & Next Steps\n"
        "- Overall risk level\n"
        "- Concrete next actions\n\n"
        "---\n\n"
        "## Conclusion\n"
        "<final summary>\n"
    )

    user = f"Project: {desc}\nEvaluation JSON:\n{json.dumps(result, indent=2)}"

    res = await llm.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
    )

    return res.choices[0].message.content


# ------------ AI REWRITE SUGGESTIONS ------------
async def generate_rewrite_suggestions(desc: str, chunks: List[str], code_smells: Dict[str, Any]) -> str:
    focus = "\n\n".join(chunks[:3])

    system = (
        "You are a senior engineer. Suggest BETTER code, not theory.\n"
        "Output STRICT MARKDOWN:\n\n"
        "## AI-Powered Rewrite Suggestions\n\n"
        "### Area 1\n"
        "**Problem:** ...\n\n"
        "**Better Approach (pseudo / snippet):**\n"
        "```language\n"
        "// improved code idea\n"
        "```\n\n"
        "### Area 2\n"
        "**Problem:** ...\n"
        "**Better Approach:** ...\n"
        "\n"
        "Only give 2–4 focused rewrite suggestions based on smells + code.\n"
    )

    user = (
        f"Project: {desc}\n\n"
        f"Code Smells JSON:\n{json.dumps(code_smells, indent=2)}\n\n"
        f"CODE SNIPPETS:\n{focus}"
    )

    res = await llm.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
    )

    return res.choices[0].message.content


# ------------ GRADING RUBRIC ------------
def rubric_from_score(score: float) -> Dict[str, Any]:
    if score >= 90:
        grade = "A+"
        summary = "Outstanding engineering quality, architecture, and hygiene."
    elif score >= 80:
        grade = "A"
        summary = "Strong codebase with minor improvements needed."
    elif score >= 70:
        grade = "B"
        summary = "Decent project, but notable issues in structure or quality."
    elif score >= 60:
        grade = "C"
        summary = "Mediocre quality; several important issues need fixing."
    else:
        grade = "D"
        summary = "High risk / weak quality; major refactors and tests required."

    return {
        "grade": grade,
        "summary": summary,
        "bands": {
            "A+": "90–100",
            "A": "80–89",
            "B": "70–79",
            "C": "60–69",
            "D": "<60"
        }
    }


# ------------ FINAL SCORE ------------
def compute_final_score(plag, logic, rel, style, pylint, structure):
    structure_score = (
        20 * structure["has_readme"] +
        20 * structure["has_requirements"] +
        15 * structure["has_tests"] +
        15 * structure["has_dockerfile"] +
        10 * structure["has_github_actions"]
    )
    return round(
        (100 - plag) * 0.3 + logic * 0.25 + rel * 0.2 + style * 0.15 +
        (pylint * 10) * 0.05 + structure_score * 0.05,
        2
    )


# ------------ PDF REPORT ------------
def generate_pdf_report(result: Dict[str, Any]) -> bytes:
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)

    c = canvas.Canvas(tmp_path, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Code Evaluation Report")
    y -= 30

    c.setFont("Helvetica", 10)

    lines = [
        f"Final Score: {result.get('final_score')}",
        f"Grade: {result.get('rubric', {}).get('grade', '-')}",
        f"Risk Score: {result.get('risk_score')}",
        "",
        f"Logic: {round(result.get('logic', 0), 2)}",
        f"Relevance: {round(result.get('relevance', 0), 2)}",
        f"Style: {round(result.get('style', 0), 2)}",
        f"Pylint: {round(result.get('pylint_score', 0), 2)}",
        f"Plagiarism: {round(result.get('plagiarism', 0), 2)}%",
        "",
        f"Files Analyzed: {result.get('files_analyzed', 0)}",
        "",
        "Structure:",
        f"  README: {result['structure'].get('has_readme')}",
        f"  Requirements: {result['structure'].get('has_requirements')}",
        f"  Tests: {result['structure'].get('has_tests')}",
        f"  Dockerfile: {result['structure'].get('has_dockerfile')}",
        f"  GitHub Actions: {result['structure'].get('has_github_actions')}",
        "",
        "Use mentor_summary_markdown in UI; this PDF is a compact technical snapshot."
    ]

    for line in lines:
        if y < 80:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)
        c.drawString(40, y, line[:120])
        y -= 14

    c.showPage()
    c.save()

    with open(tmp_path, "rb") as f:
        data = f.read()

    os.remove(tmp_path)
    return data


# ------------ BLOCKING ORCHESTRATOR (NO LLM) ------------
def evaluate_repo_blocking(url: str, desc: str):
    repo = clone_repo(url)
    try:
        chunks = get_code_chunks(repo)
        radon_raw, pylint_score = static_analysis(repo)
        plag = plagiarism_score(repo)
        structure = analyze_structure(repo)

        return repo, chunks, radon_raw, pylint_score, plag, structure
    except Exception as e:
        safe_rmtree(repo)
        raise e


# ------------ FASTAPI ENDPOINT ------------
@router.post("/evaluate")
async def evaluate_repo(request: Request):
    try:
        data = await request.json()
    except:
        raise HTTPException(400, "Invalid or empty JSON body")

    url = data.get("github_url")
    desc = data.get("project_desc", "")

    if not url:
        raise HTTPException(400, "github_url required")

    loop = asyncio.get_event_loop()
    repo, chunks, radon_raw, pylint_score, plag, structure = await loop.run_in_executor(
        executor,
        evaluate_repo_blocking,
        url,
        desc
    )

    try:
        logic, rel, style, llm_fb = await llm_code_rating(desc, chunks)

        code_smells = detect_code_smells(radon_raw, pylint_score, plag, structure)
        risk_score = compute_risk_score(plag, pylint_score, code_smells, structure)
        final_score = compute_final_score(plag, logic, rel, style, pylint_score, structure)
        rubric = rubric_from_score(final_score)

        result: Dict[str, Any] = {
            "final_score": final_score,
            "rubric": rubric,
            "risk_score": risk_score,
            "structure": structure,
            "plagiarism": plag,
            "logic": logic,
            "relevance": rel,
            "style": style,
            "pylint_score": pylint_score,
            "code_smells": code_smells,
            "llm_feedback": llm_fb,
            "files_analyzed": len(chunks),
        }

        mentor_md = await generate_markdown_mentor(desc, result)
        result["mentor_summary_markdown"] = mentor_md

        rewrite_suggestions_md = await generate_rewrite_suggestions(desc, chunks, code_smells)
        result["rewrite_suggestions_markdown"] = rewrite_suggestions_md

        pdf_bytes = generate_pdf_report(result)
        result["report_pdf_base64"] = base64.b64encode(pdf_bytes).decode("utf-8")

        return JSONResponse(result)

    finally:
        safe_rmtree(repo)

@router.get("/download-report/{evaluation_id}")
async def download_pdf_report(evaluation_id: str):
    try:
        obj_id = ObjectId(evaluation_id)
    except:
        raise HTTPException(400, "Invalid evaluation_id")

    record = db["github_evaluations"].find_one({"_id": obj_id})
    if not record:
        raise HTTPException(404, "Evaluation not found")

    result = record.get("result")
    if not result or "report_pdf_base64" not in result:
        raise HTTPException(400, "PDF is not generated for this evaluation")

    pdf_base64 = result["report_pdf_base64"]

    try:
        pdf_bytes = base64.b64decode(pdf_base64)
    except:
        raise HTTPException(500, "Invalid PDF data")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=evaluation_report_{evaluation_id}.pdf"
        }
    )