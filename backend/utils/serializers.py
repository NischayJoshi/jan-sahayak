# utils/serializers.py
from bson import ObjectId

def serialize_doc(doc: dict) -> dict:
    if not doc:
        return doc
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def serialize_docs(docs):
    return [serialize_doc(d) for d in docs]

def serialize_docs(docs):
    return [serialize_doc(d) for d in docs]