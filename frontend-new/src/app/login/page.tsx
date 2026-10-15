import type { Metadata } from "next";

import LoginForm from "@/components/auth/LoginForm";

export const metadata: Metadata = {
  title: "Sign in — AI Stock Studio",
};

/** Standalone sign-in route — the form owns the layout here. */
export default function LoginPage() {
  return <LoginForm />;
}
