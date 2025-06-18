export class BillingError extends Error {
  status: number;
  detail: { message: string; [key: string]: any }; // Allow other properties in detail

  constructor(
    status: number,
    detail: { message: string; [key: string]: any },
    message?: string,
  ) {
    super(message || detail.message || `Billing Error: ${status}`);
    this.name = "BillingError";
    this.status = status;
    this.detail = detail;

    // Set the prototype explicitly.
    Object.setPrototypeOf(this, BillingError.prototype);
  }
}
