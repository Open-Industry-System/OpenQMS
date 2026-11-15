export class AuthGenerationChangedError extends Error {
  constructor() {
    super("Access token changed in another tab");
    this.name = "AuthGenerationChangedError";
  }
}

export function isAuthGenerationChangedError(error: unknown): error is AuthGenerationChangedError {
  return error instanceof AuthGenerationChangedError;
}
