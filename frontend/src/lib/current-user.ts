let inFlight: Promise<Response> | undefined;

// Share only concurrent checks: subsequent calls must revalidate the session.
export async function fetchCurrentUser(): Promise<Response> {
  inFlight ??= fetch("/api/me", { credentials: "include" }).finally(() => {
    inFlight = undefined;
  });
  return (await inFlight).clone();
}
