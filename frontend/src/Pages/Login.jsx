import { useState } from "react";
import { motion } from "framer-motion";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FiGithub } from "react-icons/fi";
import { FcGoogle } from "react-icons/fc";
import api from "@/utils/api"; 

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  
  const [loading, setLoading] = useState(false);
  const [errorMsg, setError] = useState("");
  const [successMsg, setSuccess] = useState("");

  const handleLogin = async () => {
    setError("");
    setSuccess("");

    if (!email.trim() || !password.trim()) {
      setError("Email & password are required.");
      return;
    }

    setLoading(true);

    try {
      const res = await api.post("/auth/login", {
        email,
        password
      });

      if (res.data?.access_token) {
        localStorage.setItem("token", res.data.access_token);
      }

      setSuccess("Login successful! Redirecting...");
      setLoading(false);

      setTimeout(() => {
        window.location.href = "/dashboard"; // redirect
      }, 800);

    } catch (err) {
      const msg = err?.response?.data?.detail || "Login failed.";
      setError(msg);
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-50 flex items-center justify-center px-4">
      
      <motion.div
        initial={{ opacity: 0, y: 25 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className="
          w-full max-w-md 
          bg-white 
          rounded-3xl 
          p-10 
          border border-neutral-100
          shadow-[0_2px_12px_rgba(0,0,0,0.04),0_24px_48px_rgba(0,0,0,0.06)]
          backdrop-blur-xl
        "
      >
        {/* HEADER */}
        <h2 className="text-3xl font-semibold text-center tracking-tight">
          Welcome Back
        </h2>
        <p className="text-neutral-600 text-center mb-8 text-sm">
          Log in to your EvalX account
        </p>

        {/* ERROR MESSAGE */}
        {errorMsg && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 p-3 text-sm rounded-xl bg-red-50 text-red-600 border border-red-200"
          >
            {errorMsg}
          </motion.div>
        )}

        {/* SUCCESS MESSAGE */}
        {successMsg && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 p-3 text-sm rounded-xl bg-green-50 text-green-600 border border-green-200"
          >
            {successMsg}
          </motion.div>
        )}

        {/* EMAIL */}
        <div>
          <label className="text-sm font-medium">Email</label>
          <Input
            className="mt-1 rounded-xl"
            placeholder="you@example.com"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        {/* PASSWORD */}
        <div className="mt-5">
          <div className="flex justify-between items-center">
            <label className="text-sm font-medium">Password</label>
            <a href="#" className="text-sm text-neutral-500 hover:underline">
              Forgot?
            </a>
          </div>
          <Input
            className="mt-1 rounded-xl"
            placeholder="••••••••"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {/* LOGIN BUTTON */}
        <Button
          disabled={loading}
          onClick={handleLogin}
          className="
            w-full mt-7 
            bg-neutral-900 text-white 
            rounded-xl 
            py-3 text-sm 
            hover:bg-black transition
            disabled:opacity-50
          "
        >
          {loading ? "Logging in..." : "Log In"}
        </Button>

        {/* DIVIDER */}
        <div className="my-8 flex items-center">
          <div className="flex-1 h-[1px] bg-neutral-200"></div>
          <span className="px-3 text-neutral-500 text-sm">OR</span>
          <div className="flex-1 h-[1px] bg-neutral-200"></div>
        </div>

        {/* SOCIAL LOGINS */}
        <div className="space-y-3">
          <Button
            variant="outline"
            className="
              w-full rounded-xl py-3 
              border-neutral-300 
              hover:bg-neutral-100 
              flex items-center justify-center gap-2
            "
          >
            <FcGoogle size={20} /> Continue with Google
          </Button>

          <Button
            variant="outline"
            className="
              w-full rounded-xl py-3 
              border-neutral-300 
              hover:bg-neutral-100 
              flex items-center justify-center gap-2
            "
          >
            <FiGithub size={20} /> Continue with GitHub
          </Button>
        </div>

        {/* FOOTER */}
        <p className="text-center text-sm mt-8 text-neutral-600">
          Don’t have an account?{" "}
          <a href="/signup" className="font-medium hover:underline">
            Create Account
          </a>
        </p>

      </motion.div>
    </div>
  );
}
