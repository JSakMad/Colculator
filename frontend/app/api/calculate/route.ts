import { NextResponse } from "next/server";

const DEFAULT_API_URL = "https://colculator-api.onrender.com";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { detail: { code: "invalid_json", message: "The calculation request is not valid JSON." } },
      { status: 400 },
    );
  }

  const apiUrl = process.env.COLCULATOR_API_URL ?? DEFAULT_API_URL;
  try {
    const upstream = await fetch(`${apiUrl.replace(/\/$/, "")}/v1/calculate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(60_000),
    });
    const payload = await upstream.json();
    return NextResponse.json(payload, { status: upstream.status });
  } catch {
    return NextResponse.json(
      {
        detail: {
          code: "api_unavailable",
          message: "The calculation service is waking up or temporarily unavailable. Please try again.",
        },
      },
      { status: 503 },
    );
  }
}
