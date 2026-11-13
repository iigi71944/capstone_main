"use client";

import { useMemo, useState } from "react";
import {
  conceptTagDocs,
  syntaxTagDocs,
} from "../app/tags";

export function useTagSearch() {
  const [syntaxSearch, setSyntaxSearch] = useState("");
  const [conceptSearch, setConceptSearch] = useState("");

  const filteredSyntaxTags = useMemo(() => {
    const keyword = syntaxSearch.trim().toLowerCase();
    if (!keyword) return syntaxTagDocs;
    return syntaxTagDocs.filter(
      (item) =>
        item.tag.toLowerCase().includes(keyword) ||
        item.desc.toLowerCase().includes(keyword)
    );
  }, [syntaxSearch]);

  const filteredConceptTags = useMemo(() => {
    const keyword = conceptSearch.trim().toLowerCase();
    if (!keyword) return conceptTagDocs;
    return conceptTagDocs.filter(
      (item) =>
        item.tag.toLowerCase().includes(keyword) ||
        item.desc.toLowerCase().includes(keyword)
    );
  }, [conceptSearch]);

  return {
    syntaxSearch,
    setSyntaxSearch,
    filteredSyntaxTags,
    conceptSearch,
    setConceptSearch,
    filteredConceptTags,
  };
}
