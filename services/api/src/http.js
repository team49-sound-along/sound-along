// Response envelope and error type shared by every route.
export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export const ok = (data, meta = {}) => ({ success: true, data, error: null, meta });
export const fail = (error, meta = {}) => ({ success: false, data: null, error, meta });

/** Wrap an async route so thrown errors reach the error handler. */
export const route = (handler) => (req, res, next) => Promise.resolve(handler(req, res)).catch(next);

export function errorHandler(logger = console) {
  // eslint-disable-next-line no-unused-vars
  return (err, req, res, _next) => {
    if (err instanceof HttpError) return res.status(err.status).json(fail(err.message));
    if (err?.type === "entity.parse.failed") return res.status(400).json(fail("The request body is not valid JSON."));
    if (err?.type === "entity.too.large") return res.status(413).json(fail("The request body is too large."));
    logger.error("unhandled error", { path: req.path, message: err?.message });
    return res.status(500).json(fail("Something went wrong on our side. Please try again."));
  };
}
