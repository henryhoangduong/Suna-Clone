import { createBrowserClient } from "@supabase/ssr";

export const createClient = () => {
  let supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  if (supabaseUrl && !supabaseUrl.startsWith("http")) {
    supabaseUrl = `http://${supabaseUrl}`;
  }
  return createBrowserClient(supabaseUrl, supabaseAnonKey);
};
