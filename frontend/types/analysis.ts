export type SyntaxTag = {
  tag: string;
  count?: number;
};

export type ConceptTag = {
  tag: string;
  score?: number;
  reason?: string;
};

export type Highlight = {
  startLine: number;
  startColumn: number;
  endLine: number;
  endColumn: number;
  kind: string;
  label: string;
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
  highlights: Highlight[];
  suggestions: Suggestion[];
  error?: string | null;
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
  summary?: string | null;
  applied_rules: string[];
  warnings: string[];
  error?: string | null;
};