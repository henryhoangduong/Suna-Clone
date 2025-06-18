import { createClient } from "@/lib/supabase/client";
import {
  handleApiError,
  handleNetworkError,
  ErrorContext,
  ApiError,
} from "./error-handler";

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "";

export interface ApiClientOptions {
  showErrors?: boolean;
  errorContext?: ErrorContext;
  timeout?: number;
}

export interface ApiResponse<T = any> {
  data?: T;
  error?: ApiError;
  success: boolean;
}
