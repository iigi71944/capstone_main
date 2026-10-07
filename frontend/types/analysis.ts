export type SyntaxTag = {
  tag: string;
  count?: number | null;
  score?: number | null;
  reason?: string | null;
};

export type ConceptTag = {
  tag: string;
  count?: number | null;
  score?: number | null;
  reason?: string | null;
};

export type Suggestion = {
  type?: string;
  message?: string;
};

export type AnalysisResponse = {
  success: boolean;
  syntax_tags: SyntaxTag[];
  concept_tags: ConceptTag[];
  metrics: Record<string, number>;
  suggestions: Suggestion[];
  error?: string | null;
};

export type FinalStyleAnalysis = {
  syntax_tags: SyntaxTag[];
  concept_tags: ConceptTag[];
  metrics: Record<string, number>;
};

export type ExecutionResult = {
  success: boolean;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  timed_out: boolean;
  blocked: boolean;
  block_reason?: string | null;
};

export type ExecutionVerification = {
  source: string;
  status: "equivalent" | "different" | "not_verified";
  equivalent: boolean | null;
  original: ExecutionResult;
  transformed: ExecutionResult;
  message: string;
};

export interface CodingStyle {
  id: string;
  name: string;
  description: string;
  syntax_tags: SyntaxTag[];
  concept_tags: ConceptTag[];
  metrics: Record<string, number>;
  created_at: string;
}

export type StyleApplyResponse = {
  success: boolean;
  original_code: string;
  transformed_code: string;

  final_analysis?: FinalStyleAnalysis | null;
  missing_syntax_tags: SyntaxTag[];
  missing_concept_tags: ConceptTag[];

  execution_verification?: ExecutionVerification | null;

  summary?: string | null;
  applied_rules: string[];
  warnings: string[];
  error?: string | null;
};