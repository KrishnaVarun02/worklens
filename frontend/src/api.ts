let csrfToken = "";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export function setCSRF(token: string) {
  csrfToken = token;
}
export async function api<T = unknown>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken;
  let response: Response;
  try {
    response = await fetch(`/api/${path.replace(/^\//, "")}`, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      "WorkLens could not reach the server. Previously loaded data is still available. Try again when the connection is restored.",
      0,
    );
  }
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : data
          ? Object.entries(data)
              .map(
                ([key, value]) =>
                  `${key.replaceAll("_", " ")}: ${Array.isArray(value) ? value.join(" ") : typeof value === "object" ? JSON.stringify(value) : value}`,
              )
              .join(" · ")
          : `Request failed (${response.status}).`;
    throw new ApiError(message, response.status);
  }
  if (data?.csrfToken) setCSRF(data.csrfToken);
  return data as T;
}
