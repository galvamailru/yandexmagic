import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.INTERNAL_API_URL || "http://backend:8000";

async function proxy(req: NextRequest, path: string[]) {
  const qs = req.nextUrl.search || "";
  const url = `${BACKEND_URL}/${path.join("/")}${qs}`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const method = req.method.toUpperCase();
  const init: RequestInit = {
    method,
    headers,
    cache: "no-store",
  };

  if (method !== "GET" && method !== "HEAD") {
    init.body = await req.text();
  }

  const upstream = await fetch(url, init);
  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
    },
  });
}

export async function GET(req: NextRequest, context: { params: { path: string[] } }) {
  return proxy(req, context.params.path);
}

export async function POST(req: NextRequest, context: { params: { path: string[] } }) {
  return proxy(req, context.params.path);
}

export async function PUT(req: NextRequest, context: { params: { path: string[] } }) {
  return proxy(req, context.params.path);
}

export async function PATCH(req: NextRequest, context: { params: { path: string[] } }) {
  return proxy(req, context.params.path);
}

export async function DELETE(req: NextRequest, context: { params: { path: string[] } }) {
  return proxy(req, context.params.path);
}
