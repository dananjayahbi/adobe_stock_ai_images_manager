/**
 * Cookie-presence gate for the studio.
 *
 * Deliberately presence-only: the backend owns validity (it answers 401 for
 * junk cookies), so middleware just keeps anonymous visitors out of the app
 * and off the API-adjacent pages. `/login` is always allowed — even with a
 * cookie present — because bouncing a stale session away from /login is how
 * redirect loops are born.
 */
import { NextResponse, type NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has("studio_session");
  const isLogin = request.nextUrl.pathname === "/login";

  if (!hasSession && !isLogin) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Pages only: skip static assets (anything with a file extension, plus
  // _next/favicon/api) — gating /bg-leather.jpg would swap the login page's
  // background for an HTML redirect body.
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico|api/|.*\\..*).*)"],
};
