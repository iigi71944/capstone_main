export type ImproveCodeResponse = {
  success: boolean;
  mode: string;
  original_code: string;
  improved_code: string;
  summary?: string | null;
  error?: string | null;
};