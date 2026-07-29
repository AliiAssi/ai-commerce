import type { InferredName, SearchMetadata } from "@/lib/api/types";

/**
 * Bilingual copy for search-specific UI only.
 *
 * §4 keeps broader storefront localization out of scope: the header, the cart and the checkout
 * stay English. What must be bilingual is the search input, the interpretation the shopper is
 * shown, and the feedback when a search goes wrong — so a shopper who types Arabic reads the
 * explanation in Arabic.
 *
 * The language is chosen from the *detected query language*, not a locale setting, because
 * there is no locale setting and the query is the only signal the shopper actually gave.
 * `mixed` reads as English, which is the storefront's own language.
 */
export type CopyLang = "en" | "ar";

export function copyLang(language: string | undefined): CopyLang {
  return language === "ar" ? "ar" : "en";
}

/** Text direction for a copy block. Search results themselves stay in the page direction. */
export function copyDir(lang: CopyLang): "rtl" | "ltr" {
  return lang === "ar" ? "rtl" : "ltr";
}

interface Copy {
  interpretedLabel: string;
  removeFilter: (label: string) => string;
  degradedNotice: string;
  noResults: { title: string; body: string };
  tooNarrow: { title: string; body: string };
  degradedEmpty: { title: string; body: string };
  browseEverything: string;
  inferred: Record<InferredName, (value: string) => string>;
}

// None of this names a provider, a model, an extension, or an error code. §12 requires the
// customer-facing copy to stay calm and useful and to expose none of that, and §5.3 forbids
// claiming a semantic match when the request fell back to lexical search — so the degraded
// wording says the search was simpler, never that it was smarter than it was.
const COPY: Record<CopyLang, Copy> = {
  en: {
    interpretedLabel: "We read your search as",
    removeFilter: (label) => `Remove filter: ${label}`,
    degradedNotice:
      "Showing basic keyword matches — the smarter search is briefly unavailable.",
    noResults: {
      title: "No matches for that search",
      body: "Try different words, or fewer of them.",
    },
    tooNarrow: {
      title: "Nothing matches all of those filters",
      body: "Remove one of the filters above, or widen the price range.",
    },
    degradedEmpty: {
      title: "No keyword matches for that search",
      body: "The smarter search is briefly unavailable, so only exact words were matched. Try again shortly, or use simpler words.",
    },
    browseEverything: "Browse everything",
    inferred: {
      category: (value) => value,
      origin: (value) => `From ${value}`,
      min_price: (value) => `Over $${value}`,
      max_price: (value) => `Under $${value}`,
      in_stock_only: () => "In stock",
      sort: (value) => `Sorted by ${SORT_LABEL_EN[value] ?? value}`,
    },
  },
  ar: {
    interpretedLabel: "فهمنا بحثك كالتالي",
    removeFilter: (label) => `إزالة الفلتر: ${label}`,
    degradedNotice: "نعرض تطابق الكلمات فقط — البحث الذكي غير متاح مؤقتاً.",
    noResults: {
      title: "لا نتائج لهذا البحث",
      body: "جرّب كلمات مختلفة، أو عدداً أقل منها.",
    },
    tooNarrow: {
      title: "لا شيء يطابق كل هذه الفلاتر",
      body: "أزل أحد الفلاتر أعلاه، أو وسّع نطاق السعر.",
    },
    degradedEmpty: {
      title: "لا تطابق للكلمات في هذا البحث",
      body: "البحث الذكي غير متاح مؤقتاً، لذلك تمت مطابقة الكلمات الحرفية فقط. حاول بعد قليل، أو استخدم كلمات أبسط.",
    },
    browseEverything: "تصفّح كل المنتجات",
    inferred: {
      category: (value) => value,
      origin: (value) => `من ${value}`,
      min_price: (value) => `فوق ${value}$`,
      max_price: (value) => `تحت ${value}$`,
      in_stock_only: () => "متوفر",
      sort: (value) => `مرتّب حسب ${SORT_LABEL_AR[value] ?? value}`,
    },
  },
};

const SORT_LABEL_EN: Record<string, string> = {
  price_asc: "lowest price",
  price_desc: "highest price",
  rating: "rating",
  newest: "newest",
  relevance: "relevance",
};

const SORT_LABEL_AR: Record<string, string> = {
  price_asc: "الأرخص",
  price_desc: "الأغلى",
  rating: "التقييم",
  newest: "الأحدث",
  relevance: "الصلة",
};

export function copyFor(lang: CopyLang): Copy {
  return COPY[lang];
}

/**
 * Whether a degraded result is worth telling the shopper about.
 *
 * `degraded` is true whenever the semantic path did not run, and that includes the case where
 * smart search is simply switched off — which is every deploy until the embedding phases land.
 * Showing "briefly unavailable" on every search for months would be both untrue and noise, and
 * a warning a shopper sees every time is a warning they stop reading.
 *
 * So the notice is reserved for degradation that is actually a fault: an unreachable search
 * service, a provider outage, an index still filling. `feature_disabled` is a configuration
 * choice, and the store is doing exactly what it was configured to do.
 *
 * The response still reports `degraded` honestly either way — §18 forbids shipping lexical
 * search under the name semantic search, and this changes what is *said to the shopper*, not
 * what the API claims or what §13 records.
 */
export function isFaultDegradation(search: SearchMetadata | undefined): boolean {
  return Boolean(search?.degraded) && search?.degraded_reason !== "feature_disabled";
}

const INFERRED_ORDER: readonly InferredName[] = [
  "category",
  "origin",
  "min_price",
  "max_price",
  "in_stock_only",
  "sort",
];

export interface Chip {
  name: InferredName;
  label: string;
}

/**
 * The removable chips for what the parser inferred (§5.2).
 *
 * Only filters the response actually reported are shown. A suppressed inference is already
 * absent from `inferred_filters` — §5.2.1 forbids reporting a filter that was not applied — so
 * this needs no second check against `ignored_inferred`.
 *
 * Order is fixed rather than object order, so removing one chip does not reshuffle the rest.
 */
export function chipsFor(search: SearchMetadata | undefined, lang: CopyLang): Chip[] {
  if (!search) return [];
  const copy = copyFor(lang);
  const chips: Chip[] = [];
  for (const name of INFERRED_ORDER) {
    const value = search.inferred_filters?.[name];
    if (value === undefined) continue;
    chips.push({ name, label: copy.inferred[name](value) });
  }
  return chips;
}
