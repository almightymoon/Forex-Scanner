"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { searchSymbols, type SymbolSearchResult } from "@/lib/api";
import { registerSymbol } from "@/lib/symbols";

interface PairSearchProps {
  customPairs: string[];
  onAdd: (symbol: string) => void;
  onRemove: (symbol: string) => void;
}

export function PairSearch({ customPairs, onAdd, onRemove }: PairSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SymbolSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setSearched(false);
      setOpen(false);
      return;
    }
    setLoading(true);
    setOpen(true);
    try {
      const data = await searchSymbols(q);
      data.forEach(registerSymbol);
      setResults(data);
      setSearched(true);
    } catch {
      setResults([]);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(query), 200);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, runSearch]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const handleAdd = (item: SymbolSearchResult) => {
    registerSymbol(item);
    onAdd(item.symbol);
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="pair-search" ref={wrapperRef}>
      <div className="pair-search-input-wrap">
        <span className="search-icon" aria-hidden>⌕</span>
        <input
          type="search"
          className="pair-search-input"
          placeholder="Search pairs — e.g. gold, USDTRY, bitcoin…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (e.target.value.trim()) setOpen(true);
          }}
          onFocus={() => {
            if (query.trim()) setOpen(true);
          }}
          aria-label="Search forex pairs and assets"
          autoComplete="off"
        />
        {loading && <span className="search-spinner btn-spinner" />}
      </div>

      {open && query.trim() && (
        <ul className="pair-search-results" role="listbox">
          {loading && (
            <li className="pair-search-empty">Searching…</li>
          )}
          {!loading && searched && results.length === 0 && (
            <li className="pair-search-empty">
              No pairs found for &ldquo;{query}&rdquo;. Try gold, EURUSD, or USDTRY.
            </li>
          )}
          {!loading && results.map((item) => {
            const added = customPairs.includes(item.symbol) || item.in_default;
            return (
              <li key={item.symbol} role="option">
                <button
                  type="button"
                  className="pair-search-item"
                  onClick={() => !added && handleAdd(item)}
                  disabled={added}
                >
                  <span className="psi-symbol">{item.short}</span>
                  <span className="psi-name">{item.name}</span>
                  <span className={`psi-cat cat-${item.category}`}>{item.category}</span>
                  {item.in_default ? (
                    <span className="psi-badge">Default</span>
                  ) : added ? (
                    <span className="psi-badge added">Added</span>
                  ) : (
                    <span className="psi-add">+ Add</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {customPairs.length > 0 && (
        <div className="custom-pairs-chips">
          {customPairs.map((sym) => (
            <span key={sym} className="pair-chip">
              {sym}
              <button
                type="button"
                className="pair-chip-remove"
                onClick={() => onRemove(sym)}
                aria-label={`Remove ${sym}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
