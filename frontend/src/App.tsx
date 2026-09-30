import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, ApiError } from "./api";

type Entity = { id: number; [key: string]: any };
type User = {
  id: number;
  username: string;
  role: string;
  employee_id: number | null;
};
type Page =
  | "overview"
  | "people"
  | "goals"
  | "skills"
  | "reviews"
  | "sources"
  | "metrics"
  | "reports"
  | "administration";
type Data = Record<string, Entity[]>;
type Option = { value: string | number; label: string };
type Field = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: Option[];
  default?: unknown;
  hint?: string;
  min?: number;
  max?: number;
  step?: number;
};
type Dialog = {
  title: string;
  description?: string;
  fields?: Field[];
  submit?: (values: Record<string, any>) => Promise<unknown>;
  submitLabel?: string;
  children?: ReactNode;
  danger?: boolean;
};
const resources = [
  "employees",
  "teams",
  "roles",
  "memberships",
  "contributions",
  "goals",
  "outcomes",
  "skills",
  "assessments",
  "roadmaps",
  "requirements",
  "corrections",
  "reviews",
  "metric-definitions",
  "snapshots",
  "work-items",
  "report-jobs",
];
const today = () => new Date().toISOString().slice(0, 10);
const label = (v: unknown) =>
  String(v ?? "")
    .replaceAll("_", " ")
    .replaceAll("-", " ");
const date = (v: unknown) =>
  v
    ? new Date(String(v)).toLocaleDateString("en", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Not recorded";
const when = (v: unknown) =>
  v
    ? new Date(String(v)).toLocaleString("en", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "Never synced";
const initial = (name: string) =>
  name
    .split(" ")
    .map((x) => x[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
const tone = (state: string) =>
  /verified|approved|success|succeeded|resolved|complete|current|active|fresh/.test(
    state,
  )
    ? "green"
    : /pending|unresolved|ambiguous|stale|insufficient|claimed|queued/.test(
          state,
        )
      ? "amber"
      : /fail|error|rejected|revoked|disabled/.test(state)
        ? "red"
        : "neutral";
function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    overview: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    people: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M21 21v-3a6 6 0 0 0-3-5" />
      </>
    ),
    goals: (
      <>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="5" />
        <circle cx="12" cy="12" r="1" />
      </>
    ),
    skills: (
      <>
        <path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5" />
      </>
    ),
    reviews: (
      <>
        <rect x="4" y="5" width="16" height="16" rx="2" />
        <path d="M9 5V3h6v2M8 13l3 3 5-6" />
      </>
    ),
    sources: (
      <>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v7c0 4 16 4 16 0V5M4 12v7c0 4 16 4 16 0v-7" />
      </>
    ),
    metrics: (
      <>
        <path d="M4 20V4M4 20h17M8 16v-4M13 16V6M18 16V9" />
      </>
    ),
    reports: (
      <>
        <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6ZM14 3v6h6M8 13h8M8 17h5" />
      </>
    ),
    administration: (
      <>
        <path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    plus: <path d="M12 5v14M5 12h14" />,
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 2M18 18A8 8 0 0 1 5 16" />
      </>
    ),
    chevron: <path d="m9 5 7 7-7 7" />,
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    external: (
      <>
        <path d="M14 3h7v7M21 3 10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6M12 7h.01" />
      </>
    ),
    logout: (
      <>
        <path d="M9 3H4v18h5M9 12h12m-4-4 4 4-4 4" />
      </>
    ),
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M7 3v4M17 3v4M3 11h18" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    download: (
      <>
        <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
      </>
    ),
    spark: (
      <>
        <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.info}
    </svg>
  );
}
function Badge({ children, state }: { children: ReactNode; state?: string }) {
  return (
    <span className={`badge ${tone(state ?? String(children))}`}>
      <i />
      {children}
    </span>
  );
}
function Empty({
  title = "Nothing here yet",
  text = "Your records will appear here as evidence is added.",
  action,
}: {
  title?: string;
  text?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name="sources" size={26} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  return (
    <span className={`avatar ${small ? "small" : ""} color-${name.length % 5}`}>
      {initial(name)}
    </span>
  );
}
function Progress({
  value,
  label: accessibleLabel,
}: {
  value: number;
  label: string;
}) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={accessibleLabel}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
function SafeLink({ href, children }: { href: unknown; children: ReactNode }) {
  return typeof href === "string" && /^https?:\/\//.test(href) ? (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <Icon name="external" size={13} />
    </a>
  ) : (
    <span>{children}</span>
  );
}
function SectionTitle({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-title">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {action}
    </div>
  );
}
function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function DialogView({
  dialog,
  close,
  done,
}: {
  dialog: Dialog;
  close: () => void;
  done: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [values, setValues] = useState<Record<string, any>>(() =>
    Object.fromEntries(
      (dialog.fields ?? []).map((f) => [
        f.key,
        f.default ?? (f.type === "checkbox" ? false : ""),
      ]),
    ),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null;
    ref.current
      ?.querySelector<HTMLElement>("input, select, textarea, button")
      ?.focus();
    document.body.style.overflow = "hidden";
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) close();
      if (e.key === "Tab") {
        const focus = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]",
          ) ?? [],
        );
        if (e.shiftKey && document.activeElement === focus[0]) {
          e.preventDefault();
          focus.at(-1)?.focus();
        }
        if (!e.shiftKey && document.activeElement === focus.at(-1)) {
          e.preventDefault();
          focus[0]?.focus();
        }
      }
    };
    window.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", key);
      prior?.focus();
    };
  }, [close, busy]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const payload = { ...values };
      for (const field of dialog.fields ?? []) {
        if (field.type === "json") {
          try {
            payload[field.key] = JSON.parse(values[field.key] || "{}");
          } catch {
            throw new Error(`${field.label} must contain valid JSON.`);
          }
        }
        if (field.type === "date" && !values[field.key])
          payload[field.key] = null;
        if (
          field.key === "credentials" &&
          !Object.keys(payload[field.key] ?? {}).length
        )
          delete payload[field.key];
        if (field.type === "list")
          payload[field.key] = String(values[field.key] || "")
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean);
        if (field.type === "number" || field.type === "relation")
          payload[field.key] =
            values[field.key] === "" ? null : Number(values[field.key]);
      }
      await dialog.submit?.(payload);
      done();
      close();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The change could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) close();
      }}
    >
      <div
        className="modal"
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
      >
        <div className="modal-head">
          <div>
            <span className="eyebrow">WORKLENS WORKSPACE</span>
            <h2 id="dialog-title">{dialog.title}</h2>
          </div>
          <button
            aria-label="Close dialog"
            className="icon-button"
            onClick={close}
            disabled={busy}
          >
            <Icon name="close" />
          </button>
        </div>
        {dialog.description && (
          <p className="dialog-description">{dialog.description}</p>
        )}
        <form onSubmit={submit}>
          <div className="modal-body">
            {dialog.children}
            {dialog.fields?.map((f) => (
              <label
                className={`field ${f.type === "checkbox" ? "checkbox" : ""}`}
                key={f.key}
              >
                <span>
                  {f.label}
                  {f.required && <b aria-hidden="true"> *</b>}
                </span>
                {f.options ? (
                  <select
                    aria-label={f.label}
                    value={values[f.key]}
                    required={f.required}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.value })
                    }
                  >
                    <option value="">Select {f.label.toLowerCase()}</option>
                    {f.options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : ["textarea", "json"].includes(f.type ?? "") ? (
                  <textarea
                    aria-label={f.label}
                    rows={f.type === "json" ? 5 : 3}
                    value={values[f.key]}
                    required={f.required}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.value })
                    }
                    spellCheck={f.type !== "json"}
                  />
                ) : f.type === "checkbox" ? (
                  <input
                    aria-label={f.label}
                    type="checkbox"
                    checked={values[f.key]}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.checked })
                    }
                  />
                ) : (
                  <input
                    aria-label={f.label}
                    type={
                      ["relation", "list"].includes(f.type ?? "")
                        ? "text"
                        : (f.type ?? "text")
                    }
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    value={values[f.key]}
                    required={f.required}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.value })
                    }
                  />
                )}
                {f.hint && <small>{f.hint}</small>}
              </label>
            ))}
          </div>
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}
          <div className="modal-footer">
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={close}
            >
              {dialog.submit ? "Cancel" : "Close"}
            </button>
            {dialog.submit && (
              <button
                type="submit"
                className={`button ${dialog.danger ? "danger" : "primary"}`}
                disabled={busy}
              >
                {busy ? "Saving…" : (dialog.submitLabel ?? "Save changes")}
                <Icon name={busy ? "clock" : "arrow"} size={17} />
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<User | null | undefined>(undefined);
  const [setup, setSetup] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [data, setData] = useState<Data>({});
  const [page, setPage] = useState<Page>("overview");
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [query, setQuery] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [reviewTab, setReviewTab] = useState("corrections");
  const [mobileNav, setMobileNav] = useState(false);
  const [roadmapId, setRoadmapId] = useState("");
  const [profileTab, setProfileTab] = useState("contributions");
  const systemAdmin = session?.role === "system_admin";
  const integrationAdmin = systemAdmin || session?.role === "integration_admin";
  const canReview =
    systemAdmin || ["manager", "reviewer"].includes(session?.role ?? "");
  const list = (key: string) => data[key] ?? [];
  const employeeName = (id: number) =>
    list("employees").find((x) => x.id === id)?.name ?? `Employee ${id}`;
  const sourceName = (id: number) =>
    list("sources").find((x) => x.id === id)?.name ?? `Source ${id}`;
  const skillName = (id: number) =>
    list("skills").find((x) => x.id === id)?.name ?? `Skill ${id}`;
  const options = (key: string): Option[] =>
    list(key).map((x) => ({
      value: x.id,
      label: x.name ?? x.title ?? String(x.id),
    }));
  const employeeField = (id?: number): Field => ({
    key: "employee",
    label: "Employee",
    type: "relation",
    required: true,
    options: options("employees"),
    default: id ?? session?.employee_id ?? "",
  });
  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 6000);
  };
  const closeDialog = useCallback(() => setDialog(null), []);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const s = await api<{ user: User | null }>("auth/session/");
        if (!active) return;
        setSession(s.user);
        if (!s.user) {
          const p = await api<{ needs_setup: boolean }>("setup/");
          if (active) setSetup(p.needs_setup);
        }
      } catch (e) {
        if (active) {
          setSession(null);
          setAuthError((e as Error).message);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, []);
  const refresh = useCallback(
    async (requested?: string[]) => {
      if (!session) return;
      setLoading(true);
      if (!requested) setError("");
      const keys = requested ?? [
        ...resources,
        ...(integrationAdmin
          ? ["sources", "sync-runs", "identities", "access-scopes"]
          : []),
        ...(systemAdmin ? ["audit-events"] : []),
      ];
      const results = await Promise.allSettled(
        keys.map((k) => api<Entity[]>(`${k}/`)),
      );
      const updated: Data = {};
      const failed: string[] = [];
      results.forEach((r, i) => {
        if (r.status === "fulfilled")
          updated[keys[i]] = Array.isArray(r.value) ? r.value : [];
        else if (r.reason instanceof ApiError && r.reason.status === 403)
          updated[keys[i]] = [];
        else failed.push(keys[i]);
      });
      setData((old) => ({ ...old, ...updated }));
      if (failed.length)
        setError(
          `Some data could not be refreshed (${failed.join(", ")}). Last loaded records remain visible. Check the server and try again.`,
        );
      setLoading(false);
    },
    [session, integrationAdmin, systemAdmin],
  );
  async function refreshAffected(path: string) {
    if (path.endsWith("/test/")) return;
    const resource = path.split("/")[0];
    if (["retention", "csv-import"].includes(resource)) return refresh();
    const affected: Record<string, string[]> = {
      sources: [
        "sources",
        "sync-runs",
        "identities",
        "contributions",
        "work-items",
        "snapshots",
      ],
      identities: ["identities", "contributions", "work-items", "snapshots"],
      employees: path.endsWith("/calculate/")
        ? ["snapshots", "metric-definitions"]
        : ["employees", "memberships"],
      contributions: ["contributions", "snapshots"],
      assessments: ["assessments", "snapshots"],
      corrections: ["corrections", "contributions", "snapshots"],
      requirements: ["requirements", "roadmaps"],
      "work-items": ["work-items", "snapshots"],
      "access-scopes": [
        "access-scopes",
        "sources",
        "contributions",
        "snapshots",
      ],
    };
    return refresh(affected[resource] ?? [resource]);
  }
  useEffect(() => {
    void refresh();
  }, [refresh]);
  async function authenticate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    const fd = new FormData(e.currentTarget);
    try {
      const res = await api<{ user: User }>(
        setup ? "setup/" : "auth/login/",
        "POST",
        Object.fromEntries(fd),
      );
      setSession(res.user);
      setSetup(false);
    } catch (e) {
      setAuthError((e as Error).message);
    } finally {
      setAuthBusy(false);
    }
  }
  async function action(
    path: string,
    body: unknown = {},
    message = "Changes saved.",
  ) {
    try {
      const result = await api(path, "POST", body);
      notify(message);
      await refreshAffected(path);
      return result;
    } catch (e) {
      notify((e as Error).message);
      throw e;
    }
  }
  function navigate(p: Page) {
    setPage(p);
    setEmployeeId(null);
    setQuery("");
    setMobileNav(false);
  }
  function openEmployee(id: number) {
    setEmployeeId(id);
    setPage("people");
    setProfileTab("contributions");
  }
  function create(
    resource: string,
    title: string,
    fields: Field[],
    description?: string,
    initial?: Entity,
  ) {
    setDialog({
      title,
      description,
      fields: fields.map((f) => ({
        ...f,
        default: initial?.[f.key] ?? f.default,
      })),
      submit: async (values) => {
        await api(
          `${resource}/${initial ? `${initial.id}/` : ""}`,
          initial ? "PATCH" : "POST",
          values,
        );
        notify(`${title} saved.`);
        await refreshAffected(resource);
      },
    });
  }
  function addContribution(id?: number) {
    create(
      "contributions",
      "Add contribution evidence",
      [
        employeeField(id),
        { key: "title", label: "Contribution", required: true },
        {
          key: "kind",
          label: "Category",
          required: true,
          default: "delivery",
          options: [
            "delivery",
            "pairing",
            "shared_delivery",
            "mentoring",
            "review",
            "documentation",
            "training",
          ].map((v) => ({ value: v, label: label(v) })),
        },
        {
          key: "occurred_on",
          label: "Evidence date",
          type: "date",
          default: today(),
          required: true,
        },
        { key: "evidence_url", label: "Evidence link", type: "url" },
        {
          key: "share",
          label: "Contribution share",
          type: "number",
          min: 0,
          max: 1,
          step: 0.05,
          default: 1,
          required: true,
          hint: "A fraction from 0 to 1. Shared work keeps separate contributors.",
        },
        {
          key: "context",
          label: "Context and contribution",
          type: "textarea",
          required: true,
        },
      ],
      "Add the evidence and your role in the outcome. A submission is a claim until a reviewer verifies it.",
    );
  }
  function addCorrection(id?: number, contribution?: Entity) {
    create(
      "corrections",
      "Request a correction",
      [
        employeeField(id),
        {
          key: "contribution",
          label: "Contribution",
          type: "relation",
          options: list("contributions")
            .filter((c) => !id || c.employee === id)
            .map((c) => ({ value: c.id, label: c.title })),
          default: contribution?.id,
        },
        {
          key: "reason",
          label: "What needs correcting?",
          required: true,
          type: "textarea",
        },
        {
          key: "requested_context",
          label: "Proposed context",
          required: true,
          type: "textarea",
        },
      ],
      "Your request is recorded for review. Approved changes preserve the original context and review history.",
    );
  }
  function addAssessment(id?: number) {
    create(
      "assessments",
      "Record a skill assessment",
      [
        employeeField(id),
        {
          key: "skill",
          label: "Skill",
          options: options("skills"),
          type: "relation",
          required: true,
        },
        {
          key: "level",
          label: "Proficiency level",
          type: "number",
          required: true,
          min: 1,
          max: 5,
          default: 1,
          hint: "1 Foundational · 2 Developing · 3 Independent · 4 Advanced · 5 Expert. Check the skill rubric before assessing.",
        },
        {
          key: "kind",
          label: "Evidence basis",
          options: ["self_declared", "evidence_supported"].map((v) => ({
            value: v,
            label: label(v),
          })),
          default: "self_declared",
          required: true,
        },
        {
          key: "assessed_on",
          label: "Assessment date",
          type: "date",
          default: today(),
          required: true,
        },
        { key: "evidence_url", label: "Supporting evidence", type: "url" },
        {
          key: "note",
          label: "Evidence and development context",
          type: "textarea",
          required: true,
        },
      ],
      "Only a separate reviewer can verify proficiency. Candidate evidence alone does not establish a skill.",
    );
  }
  function addGoal(id?: number, goal?: Entity) {
    create(
      "goals",
      goal ? "Update goal" : "Create a goal",
      [
        employeeField(id),
        { key: "title", label: "Goal", required: true },
        {
          key: "description",
          label: "Success criteria",
          type: "textarea",
          required: true,
        },
        { key: "due_date", label: "Target date", type: "date", required: true },
        {
          key: "progress",
          label: "Progress (%)",
          type: "number",
          min: 0,
          max: 100,
          default: 0,
          required: true,
        },
        {
          key: "status",
          label: "Status",
          required: true,
          default: "active",
          options: ["active", "completed", "paused"].map((v) => ({
            value: v,
            label: label(v),
          })),
        },
      ],
      "Agree clear outcomes and evidence with the employee.",
      goal,
    );
  }
  function addOutcome(id?: number) {
    create(
      "outcomes",
      "Record a business outcome",
      [
        employeeField(id),
        {
          key: "goal",
          label: "Related goal",
          type: "relation",
          options: options("goals"),
        },
        { key: "title", label: "Outcome", required: true },
        {
          key: "impact",
          label: "Documented impact",
          type: "textarea",
          required: true,
        },
        {
          key: "evidence_url",
          label: "Supporting evidence",
          type: "url",
          required: true,
        },
        {
          key: "occurred_on",
          label: "Outcome date",
          type: "date",
          default: today(),
          required: true,
        },
      ],
      "Impact claims require evidence and reviewer verification. Activity counts do not establish business value.",
    );
  }
  function addEmployee(initialEmployee?: Entity) {
    create(
      "employees",
      initialEmployee ? "Edit employee" : "Add an employee",
      [
        { key: "stable_id", label: "Stable employee ID", required: true },
        { key: "name", label: "Full name", required: true },
        { key: "email", label: "Work email", type: "email", required: true },
        {
          key: "role",
          label: "Role template",
          type: "relation",
          options: options("roles"),
        },
        {
          key: "team",
          label: "Team",
          type: "relation",
          options: options("teams"),
        },
        {
          key: "manager",
          label: "Manager",
          type: "relation",
          options: options("employees"),
        },
        {
          key: "capacity",
          label: "Available capacity (%)",
          type: "number",
          min: 0,
          max: 100,
          default: 100,
        },
        {
          key: "context",
          label: "Work context",
          type: "textarea",
          hint: "Record onboarding or responsibilities; omit sensitive reasons for absence.",
        },
        {
          key: "access_role",
          label: "Access role",
          default: "employee",
          required: true,
          options: [
            "employee",
            "manager",
            "reviewer",
            "integration_admin",
            "system_admin",
          ].map((v) => ({ value: v, label: label(v) })),
        },
      ],
      "Use a stable internal ID. Matching email addresses never grant source access.",
      initialEmployee,
    );
  }
  function addSource(source?: Entity) {
    create(
      "sources",
      source ? "Configure source" : "Connect a source",
      [
        { key: "name", label: "Connection name", required: true },
        {
          key: "kind",
          label: "Source system",
          required: true,
          default: "fixture",
          options: ["fixture", "jira", "bitbucket", "confluence"].map((v) => ({
            value: v,
            label: v === "fixture" ? "Synthetic local fixture" : label(v),
          })),
        },
        {
          key: "deployment",
          label: "Deployment type",
          required: true,
          default: "fixture",
          options: ["fixture", "cloud", "data_center"].map((v) => ({
            value: v,
            label: label(v),
          })),
        },
        {
          key: "base_url",
          label: "Approved endpoint",
          type: "url",
          hint: "External URLs must be allowed in the server’s network configuration. Leave blank for a fixture.",
        },
        {
          key: "scopes",
          label: "Projects, repositories or spaces",
          type: "list",
          default: source?.scopes?.join(", ") ?? "",
          hint: "Explicit allowlist, separated by commas. Required for live sources.",
        },
        {
          key: "fields",
          label: "Permitted source fields",
          type: "list",
          default: source?.fields?.join(", ") ?? "",
          hint: "Explicit field allowlist, separated by commas.",
        },
        {
          key: "config",
          label: "Adapter configuration (JSON)",
          type: "json",
          default: JSON.stringify(source?.config ?? {}, null, 2),
          hint: "Use the administrator guide for supported adapter fields.",
        },
        {
          key: "credentials",
          label: "Read-only credentials (JSON)",
          type: "json",
          default: "{}",
          hint: "Configured locally, encrypted on the server and never returned. Omit to preserve existing credentials.",
        },
        {
          key: "retention_days",
          label: "Retention (days)",
          type: "number",
          min: 1,
          max: 3650,
          default: 365,
        },
        {
          key: "enabled",
          label: "Enable synchronization",
          type: "checkbox",
          default: true,
        },
      ],
      "Each source needs its own read-only credentials and allowlists. Cloud-connected installations use approved external work systems.",
      source
        ? {
            ...source,
            scopes: source.scopes.join(", "),
            fields: source.fields.join(", "),
            config: JSON.stringify(source.config, null, 2),
          }
        : undefined,
    );
  }
  function metricDetail(metric: Entity) {
    const definition = list("metric-definitions").find(
      (d) => d.id === metric.definition,
    );
    setDialog({
      title: metric.metric_name ?? definition?.name ?? "Metric explanation",
      description: definition?.definition,
      children: (
        <div className="metric-explanation">
          <Badge state={metric.status}>{label(metric.status)}</Badge>
          <dl>
            <dt>Value</dt>
            <dd>
              {metric.value === null
                ? metric.status === "available"
                  ? "Inspect dimension-specific evidence below"
                  : "Insufficient evidence"
                : metric.value}
            </dd>
            <dt>Formula version</dt>
            <dd>{metric.metric_version ?? definition?.version ?? "—"}</dd>
            <dt>Period</dt>
            <dd>
              {date(metric.window_start)} – {date(metric.window_end)}
            </dd>
            <dt>Intended use</dt>
            <dd>
              {definition?.intended_use ??
                "See the versioned definition below."}
            </dd>
            <dt>Formula</dt>
            <dd>
              <code>
                {metric.details?.formula ??
                  definition?.formula ??
                  "Recorded in metric details"}
              </code>
            </dd>
            <dt>Evidence basis</dt>
            <dd>{label(metric.details?.origin ?? "calculated")}</dd>
            <dt>Sample size</dt>
            <dd>{metric.details?.sample_size ?? "Not applicable"}</dd>
            <dt>Numerator / denominator</dt>
            <dd>
              {metric.details?.numerator ?? "Unknown"} /{" "}
              {metric.details?.denominator ?? "Not applicable"}
            </dd>
          </dl>
          {Array.isArray(metric.details?.source_freshness) &&
            metric.details.source_freshness.length > 0 && (
              <>
                <h3>Source freshness at calculation</h3>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Source</th>
                        <th>Last synchronized</th>
                        <th>Freshness</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metric.details.source_freshness.map((source: Entity) => (
                        <tr key={source.id}>
                          <td>{source.name}</td>
                          <td>{when(source.last_success_at)}</td>
                          <td>
                            <Badge state={source.stale ? "stale" : "fresh"}>
                              {source.stale
                                ? "Stale evidence"
                                : "Current at calculation"}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          {Array.isArray(metric.details?.inputs) &&
            metric.details.inputs.length > 0 && (
              <>
                <h3>Supporting evidence</h3>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Input</th>
                        <th>Date</th>
                        <th>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metric.details.inputs.map(
                        (input: Record<string, any>, index: number) => (
                          <tr key={index}>
                            <td>
                              {input.title ??
                                input.skill ??
                                `Input ${index + 1}`}
                            </td>
                            <td>
                              {date(
                                input.occurred_on ??
                                  input.assessed_on ??
                                  input.completed_at ??
                                  input.due_date ??
                                  input.assessment?.assessed_on,
                              )}
                            </td>
                            <td>
                              <SafeLink
                                href={
                                  input.evidence_url ??
                                  input.assessment?.evidence_url
                                }
                              >
                                {input.evidence_url ||
                                input.assessment?.evidence_url
                                  ? "View evidence"
                                  : "Structured record"}
                              </SafeLink>
                            </td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          <h3>Calculation record</h3>
          <p className="muted">
            Inputs, sample sizes, exclusions and freshness are preserved with
            this snapshot.
          </p>
          <pre>{JSON.stringify(metric.details, null, 2)}</pre>
        </div>
      ),
    });
  }
  function evidenceDetail(evidence: Entity) {
    setDialog({
      title: evidence.title,
      description: `${employeeName(evidence.employee)} · ${date(evidence.occurred_on)}`,
      children: (
        <div className="metric-explanation">
          <div className="inline">
            <Badge>{label(evidence.origin)}</Badge>
            <Badge state={evidence.verified ? "verified" : "pending"}>
              {evidence.verified ? "Reviewer verified" : "Unverified"}
            </Badge>
          </div>
          <p>{evidence.context || "No additional context recorded."}</p>
          <dl>
            <dt>Category</dt>
            <dd>{label(evidence.kind)}</dd>
            <dt>Contribution share</dt>
            <dd>
              {evidence.share == null
                ? "Not established"
                : `${Math.round(evidence.share * 100)}%`}
            </dd>
            <dt>Evidence</dt>
            <dd>
              <SafeLink href={evidence.evidence_url}>
                {evidence.evidence_url
                  ? "Open source record"
                  : "No link recorded"}
              </SafeLink>
            </dd>
            <dt>Reviewer</dt>
            <dd>
              {evidence.reviewer
                ? `Reviewer #${evidence.reviewer}`
                : "Awaiting review"}
            </dd>
          </dl>
          <button
            className="button secondary"
            onClick={() => addCorrection(evidence.employee, evidence)}
          >
            Request a correction
          </button>
        </div>
      ),
    });
  }
  const nav: { page: Page; text: string; group?: string }[] = [
    { page: "overview", text: "Overview", group: "WORKSPACE" },
    { page: "people", text: "People & teams" },
    { page: "goals", text: "Goals & outcomes" },
    { page: "skills", text: "Skills & roadmap" },
    { page: "reviews", text: "Reviews", group: "EVIDENCE & INSIGHTS" },
    { page: "metrics", text: "Metric dictionary" },
    { page: "reports", text: "Reports" },
    ...(integrationAdmin
      ? [{ page: "sources" as Page, text: "Data sources", group: "MANAGEMENT" }]
      : []),
    ...(systemAdmin
      ? [{ page: "administration" as Page, text: "Administration" }]
      : []),
  ];
  const visibleNav =
    session?.role === "integration_admin"
      ? nav.filter((item) =>
          ["overview", "sources", "metrics"].includes(item.page),
        )
      : nav;
  const me = list("employees").find((e) => e.id === session?.employee_id);
  const employees = list("employees").filter(
    (e) =>
      (!query ||
        `${e.name} ${e.email} ${e.role_name}`
          .toLowerCase()
          .includes(query.toLowerCase())) &&
      (!teamFilter || String(e.team) === teamFilter),
  );
  const pending = list("corrections").filter((c) => c.status === "pending");
  const selectedEmployee = list("employees").find((e) => e.id === employeeId);
  const roadmap =
    list("roadmaps").find((r) => String(r.id) === roadmapId) ??
    list("roadmaps").find((r) => r.active) ??
    list("roadmaps")[0];
  const requirements = list("requirements").filter(
    (r) => r.roadmap === roadmap?.id,
  );
  const latestSnapshots = useMemo(() => {
    const map = new Map<string, Entity>();
    for (const s of data.snapshots ?? []) {
      const key = `${s.employee}:${s.metric_key ?? s.definition}`;
      if (
        !map.has(key) ||
        String(s.created_at) > String(map.get(key)?.created_at)
      )
        map.set(key, s);
    }
    return [...map.values()];
  }, [data.snapshots]);
  const statusCount = (kind: string) =>
    list("contributions").filter((c) => c.kind === kind).length;
  function evidenceRows(evidence: Entity[], concise = false) {
    return evidence.length ? (
      <div className="evidence-list">
        {evidence.map((c) => (
          <button
            className="evidence-row"
            key={c.id}
            onClick={() => evidenceDetail(c)}
          >
            <span className={`evidence-icon ${c.verified ? "verified" : ""}`}>
              <Icon
                name={
                  c.kind === "mentoring" || c.kind === "collaboration"
                    ? "people"
                    : c.kind === "documentation"
                      ? "reports"
                      : "goals"
                }
                size={19}
              />
            </span>
            <span className="evidence-text">
              <strong>{c.title}</strong>
              <span>
                {concise ? employeeName(c.employee) : label(c.kind)}
                <i>·</i>
                {date(c.occurred_on)}
                <i>·</i>
                {label(c.origin)}
              </span>
            </span>
            <Badge state={c.verified ? "verified" : "pending"}>
              {c.verified ? "Verified" : "Needs review"}
            </Badge>
            <Icon name="chevron" size={16} />
          </button>
        ))}
      </div>
    ) : (
      <Empty
        title="Evidence builds the picture"
        text="Add a contribution or synchronize an approved source to begin."
      />
    );
  }
  function metricCards(metrics: Entity[]) {
    return metrics.length ? (
      <div className="metric-grid">
        {metrics.map((m) => (
          <button
            className="metric-card"
            key={m.id}
            onClick={() => metricDetail(m)}
          >
            <span className="metric-label">
              {m.metric_name ??
                list("metric-definitions").find((d) => d.id === m.definition)
                  ?.name ??
                label(m.metric_key)}
            </span>
            <strong>
              {m.value === null || m.value === undefined
                ? m.status === "available"
                  ? (m.details?.verified_skill_count ??
                    m.details?.evidence_count ??
                    "By category")
                  : "—"
                : Number.isInteger(m.value)
                  ? m.value
                  : Number(m.value).toFixed(1)}
              {m.value !== null &&
                /delivery|quality|alignment|business/.test(
                  m.metric_key ?? "",
                ) && <small>%</small>}
            </strong>
            <Badge state={m.status}>{label(m.status)}</Badge>
            {m.details?.source_freshness?.some(
              (source: { stale?: boolean }) => source.stale,
            ) && (
              <span className="metric-freshness">
                Includes stale source data
              </span>
            )}
            <span className="metric-foot">
              {m.details?.sample_size !== undefined
                ? `${m.details.sample_size} observations`
                : "View calculation"}
              <Icon name="arrow" size={15} />
            </span>
          </button>
        ))}
      </div>
    ) : (
      <div className="notice">
        <Icon name="info" />
        <span>
          No metrics have been calculated. Calculate a snapshot to see versioned
          results and evidence coverage.
        </span>
      </div>
    );
  }
  function employeeTable(people: Entity[], compact = false) {
    return people.length ? (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Employee</th>
              <th scope="col">Role / team</th>
              <th scope="col">Evidence</th>
              <th scope="col">Verified skills</th>
              {!compact && <th scope="col">Capacity</th>}
              <th scope="col">
                <span className="sr-only">Profile</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {people.map((e) => {
              const count = list("contributions").filter(
                (c) => c.employee === e.id,
              ).length;
              const skills = new Set(
                list("assessments")
                  .filter((a) => a.employee === e.id && a.kind === "verified")
                  .map((a) => a.skill),
              ).size;
              return (
                <tr key={e.id}>
                  <td>
                    <button
                      className="person-cell"
                      onClick={() => openEmployee(e.id)}
                    >
                      <Avatar name={e.name} />
                      <span>
                        <strong>{e.name}</strong>
                        <small>{e.stable_id}</small>
                      </span>
                    </button>
                  </td>
                  <td>
                    <span className="cell-main">
                      {e.role_name ??
                        list("roles").find((r) => r.id === e.role)?.name ??
                        "Role not assigned"}
                    </span>
                    <small>
                      {e.team_name ??
                        list("teams").find((t) => t.id === e.team)?.name ??
                        "No team"}
                    </small>
                  </td>
                  <td>
                    <span className="count-pill">{count}</span>
                    <small>records</small>
                  </td>
                  <td>
                    {skills ? (
                      <span className="skill-count">
                        <i />
                        {skills} verified
                      </span>
                    ) : (
                      <span className="muted">Not assessed</span>
                    )}
                  </td>
                  {!compact && (
                    <td>
                      {e.capacity}%
                      <small>{e.context || "Available capacity"}</small>
                    </td>
                  )}
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`View ${e.name}`}
                      onClick={() => openEmployee(e.id)}
                    >
                      <Icon name="arrow" size={17} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    ) : (
      <Empty
        title="No employees found"
        text="Try another search, change the team filter, or add your first employee."
      />
    );
  }
  function overview() {
    if (session?.role === "integration_admin")
      return (
        <>
          <SectionTitle
            eyebrow="INTEGRATION ADMINISTRATION"
            title="Trusted sources. Traceable evidence."
            text="Configure approved connections and resolve source identities within your integration responsibilities."
            action={
              <button
                className="button primary"
                onClick={() => navigate("sources")}
              >
                Manage data sources
                <Icon name="arrow" size={17} />
              </button>
            }
          />
          <div className="mini-stats">
            <span>
              <strong>{list("sources").length}</strong>Configured sources
            </span>
            <span>
              <strong>
                {
                  list("identities").filter((identity) =>
                    ["ambiguous", "unresolved"].includes(identity.status),
                  ).length
                }
              </strong>
              Identities to review
            </span>
            <span>
              <strong>{list("access-scopes").length}</strong>Team visibility
              scopes
            </span>
          </div>
          <Panel
            title="Keep the evidence trustworthy"
            subtitle="Independent credentials, explicit allowlists and reviewable synchronization."
          >
            <div className="principle-grid" style={{ padding: "0 22px" }}>
              <article>
                <Icon name="sources" />
                <h3>Configure approved endpoints</h3>
                <p>
                  Each integration uses separate read-only credentials and field
                  and scope allowlists.
                </p>
              </article>
              <article>
                <Icon name="people" />
                <h3>Resolve identities deliberately</h3>
                <p>
                  Map accounts to stable employee IDs. Classify service accounts
                  without attributing automated activity to a person.
                </p>
              </article>
              <article>
                <Icon name="administration" />
                <h3>Review access and retention</h3>
                <p>
                  Reconcile changed permissions, remove retained data, and
                  inspect sync failures before using evidence.
                </p>
              </article>
            </div>
          </Panel>
        </>
      );
    const contributions = list("contributions");
    const verified = contributions.filter((c) => c.verified).length;
    const categories = [...new Set(contributions.map((c) => c.kind))];
    const coverage = contributions.length
      ? Math.round((100 * verified) / contributions.length)
      : null;
    return (
      <>
        <SectionTitle
          eyebrow="YOUR WORKSPACE, IN PERSPECTIVE"
          title={
            session?.role === "employee"
              ? `Your contribution, ${me?.name?.split(" ")[0] ?? session.username}.`
              : "See the work. Support the people."
          }
          text="A clearer view of contributions, skills and the evidence behind them."
          action={
            <button
              className="button primary"
              onClick={() => addContribution()}
            >
              <Icon name="plus" size={17} />
              Add evidence
            </button>
          }
        />
        <div className="overview-banner">
          <div className="banner-mark">
            <Icon name="spark" size={27} />
          </div>
          <div>
            <strong>Good decisions start with the whole picture.</strong>
            <p>
              Explore separate dimensions of contribution. Every insight has
              evidence, context and room for review.
            </p>
          </div>
          <button onClick={() => navigate("metrics")}>
            How WorkLens works <Icon name="arrow" size={17} />
          </button>
        </div>
        {systemAdmin &&
          (!list("employees").length || !list("sources").length) && (
            <div className="setup-strip">
              <Icon name="check" />
              <div>
                <strong>Set up your workspace</strong>
                <p>
                  Add people and role templates, connect a scoped source, then
                  review identities and evidence.
                </p>
              </div>
              <button
                className="button secondary"
                onClick={() =>
                  navigate(
                    list("employees").length ? "sources" : "administration",
                  )
                }
              >
                Continue setup
                <Icon name="arrow" size={15} />
              </button>
            </div>
          )}
        <div className="stat-grid">
          <div className="stat-card">
            <div>
              <span>People in your scope</span>
              <Icon name="people" />
            </div>
            <strong>
              {list("employees").length.toString().padStart(2, "0")}
            </strong>
            <small>{list("teams").length} teams · role-scoped access</small>
          </div>
          <div className="stat-card">
            <div>
              <span>Contribution evidence</span>
              <Icon name="reports" />
            </div>
            <strong>{contributions.length}</strong>
            <small>{verified} reviewer verified</small>
          </div>
          <div className="stat-card">
            <div>
              <span>Evidence review coverage</span>
              <Icon name="administration" />
            </div>
            <strong>
              {coverage === null ? "—" : coverage}
              <em>{coverage === null ? "" : "%"}</em>
            </strong>
            <small>
              {coverage === null
                ? "No evidence recorded yet"
                : "Verified records / all contribution records"}
            </small>
          </div>
          <div className="stat-card attention">
            <div>
              <span>Awaiting a conversation</span>
              <Icon name="reviews" />
            </div>
            <strong>{pending.length.toString().padStart(2, "0")}</strong>
            <button className="text-button" onClick={() => navigate("reviews")}>
              Correction requests
              <Icon name="arrow" size={15} />
            </button>
          </div>
        </div>
        <div className="two-col">
          <Panel
            title="The contribution picture"
            subtitle="Evidence by category · your authorized scope"
            action={<span className="pill">All recorded evidence</span>}
          >
            <div className="chart-legend">
              <span>
                <i className="legend-verified" />
                Reviewer verified
              </span>
              <span>
                <i className="legend-pending" />
                Awaiting verification
              </span>
            </div>
            {categories.length ? (
              <div className="bar-chart">
                {categories.slice(0, 6).map((kind) => {
                  const total = statusCount(kind);
                  const v = contributions.filter(
                    (c) => c.kind === kind && c.verified,
                  ).length;
                  const max = Math.max(...categories.map(statusCount), 1);
                  return (
                    <div className="bar-row" key={kind}>
                      <span>{label(kind)}</span>
                      <div
                        className="bar-track"
                        role="img"
                        aria-label={`${label(kind)}: ${v} verified, ${total - v} unverified records`}
                      >
                        <div
                          className="bar-value"
                          style={{ width: `${(100 * total) / max}%` }}
                        >
                          <span style={{ width: `${(100 * v) / total}%` }} />
                        </div>
                      </div>
                      <strong>{total}</strong>
                    </div>
                  );
                })}
              </div>
            ) : (
              <Empty
                title="Your evidence picture will grow here"
                text="Import or record contributions to see the distribution."
              />
            )}
            <div className="panel-note">
              <Icon name="info" size={15} />
              Volume describes available evidence. It does not measure
              contribution quality.
            </div>
          </Panel>
          <Panel
            title="What needs your attention"
            subtitle="Small actions that improve the picture"
          >
            <div className="attention-list">
              <button onClick={() => navigate("reviews")}>
                <span className="attention-symbol amber">
                  <Icon name="reviews" />
                </span>
                <span>
                  <strong>Review the missing context</strong>
                  <small>
                    {pending.length} correction requests awaiting review
                  </small>
                </span>
                <Icon name="chevron" size={16} />
              </button>
              <button onClick={() => navigate("skills")}>
                <span className="attention-symbol green">
                  <Icon name="skills" />
                </span>
                <span>
                  <strong>Make development intentional</strong>
                  <small>
                    {roadmap
                      ? roadmap.name
                      : "Define your first skills roadmap"}
                  </small>
                </span>
                <Icon name="chevron" size={16} />
              </button>
              <button
                onClick={() =>
                  navigate(integrationAdmin ? "sources" : "metrics")
                }
              >
                <span className="attention-symbol blue">
                  <Icon name="sources" />
                </span>
                <span>
                  <strong>
                    {integrationAdmin
                      ? "Keep the evidence current"
                      : "Understand every calculation"}
                  </strong>
                  <small>
                    {integrationAdmin
                      ? `${list("sources").length} configured sources · inspect sync coverage`
                      : "Open definitions, samples and limitations"}
                  </small>
                </span>
                <Icon name="chevron" size={16} />
              </button>
            </div>
            <div className="quiet-callout">
              <span className="small-caps">A PEOPLE-FIRST PERSPECTIVE</span>
              <p>
                Missing evidence is unknown.
                <br />
                It is never a zero.
              </p>
              <button
                className="text-button"
                onClick={() => navigate("metrics")}
              >
                Read the metric dictionary
                <Icon name="arrow" size={15} />
              </button>
            </div>
          </Panel>
        </div>
        <Panel
          title="People, with context"
          subtitle="Contribution and development across your authorized team"
          action={
            <button className="text-button" onClick={() => navigate("people")}>
              View all people
              <Icon name="arrow" size={16} />
            </button>
          }
        >
          {employeeTable(
            list("employees")
              .filter((e) => e.active)
              .slice(0, 5),
            true,
          )}
        </Panel>
        <div className="two-col bottom-grid">
          <Panel
            title="Recent evidence"
            subtitle="A traceable record of meaningful work"
            action={
              <button className="text-button" onClick={() => addContribution()}>
                Add evidence
                <Icon name="plus" size={15} />
              </button>
            }
          >
            {evidenceRows(
              [...contributions]
                .sort((a, b) =>
                  String(b.occurred_on).localeCompare(String(a.occurred_on)),
                )
                .slice(0, 4),
              true,
            )}
          </Panel>
          <section className="roadmap-feature">
            <span className="eyebrow">BUILD TOWARD WHAT’S NEXT</span>
            <div className="roadmap-art" aria-hidden="true">
              <span />
              <span />
              <span />
              <Icon name="skills" size={38} />
            </div>
            <h2>{roadmap?.name ?? "A shared direction for growth."}</h2>
            <p>
              {roadmap?.description ??
                "Define the skills your company will need, then connect verified evidence to practical development actions."}
            </p>
            <button className="button light" onClick={() => navigate("skills")}>
              Explore the roadmap
              <Icon name="arrow" size={17} />
            </button>
            {roadmap && (
              <small>
                Target {date(roadmap.target_date)} · Version {roadmap.version}
              </small>
            )}
          </section>
        </div>
      </>
    );
  }
  function peoplePage() {
    return (
      <>
        <SectionTitle
          eyebrow="PEOPLE & TEAMS"
          title="People behind the progress."
          text="Understand each person’s contribution in the context of their role and team."
          action={
            systemAdmin ? (
              <button className="button primary" onClick={() => addEmployee()}>
                <Icon name="plus" size={17} />
                Add employee
              </button>
            ) : undefined
          }
        />
        <div className="toolbar">
          <label className="search">
            <Icon name="search" size={18} />
            <input
              aria-label="Search employees"
              placeholder="Search people, roles or emails…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Filter by team"
            value={teamFilter}
            onChange={(e) => setTeamFilter(e.target.value)}
          >
            <option value="">All teams</option>
            {list("teams").map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <span className="muted">{employees.length} people</span>
        </div>
        <Panel
          title="Employee directory"
          subtitle="No rankings. Evidence, context and development."
        >
          {employeeTable(employees)}
        </Panel>
        <div className="team-cards">
          {list("teams").map((t) => (
            <button key={t.id} onClick={() => setTeamFilter(String(t.id))}>
              <span className="team-symbol">
                <Icon name="people" />
              </span>
              <h3>{t.name}</h3>
              <p>{t.description || "Team workspace"}</p>
              <span>
                {list("employees").filter((e) => e.team === t.id).length} people
                <Icon name="arrow" size={16} />
              </span>
            </button>
          ))}
        </div>
      </>
    );
  }
  function profile() {
    if (!selectedEmployee)
      return (
        <Empty
          title="Employee unavailable"
          text="This record is outside your scope or has been removed."
        />
      );
    const e = selectedEmployee;
    const ev = list("contributions").filter((c) => c.employee === e.id);
    const metrics = latestSnapshots.filter((m) => m.employee === e.id);
    const assessments = list("assessments").filter((a) => a.employee === e.id);
    return (
      <>
        <button className="back-link" onClick={() => setEmployeeId(null)}>
          ← People & teams
        </button>
        <div className="profile-head">
          <Avatar name={e.name} />
          <div>
            <span className="eyebrow">CONTRIBUTION & DEVELOPMENT</span>
            <h1>{e.name}</h1>
            <p>
              {e.role_name ??
                list("roles").find((r) => r.id === e.role)?.name ??
                "Role not assigned"}
              <i>·</i>
              {e.team_name ??
                list("teams").find((t) => t.id === e.team)?.name ??
                "No team"}
              <i>·</i>
              {e.stable_id}
            </p>
          </div>
          <div className="profile-actions">
            <button
              className="button secondary"
              onClick={() => addCorrection(e.id)}
            >
              Request correction
            </button>
            <button
              className="button primary"
              onClick={() => addContribution(e.id)}
            >
              <Icon name="plus" size={16} />
              Add evidence
            </button>
          </div>
        </div>
        <div className="profile-context">
          <span>
            <Icon name="people" size={16} />
            Manager: {e.manager ? employeeName(e.manager) : "Not assigned"}
          </span>
          <span>{e.capacity}% available capacity</span>
          <span>{e.context || "No additional work context recorded"}</span>
          {systemAdmin && (
            <button className="text-button" onClick={() => addEmployee(e)}>
              Edit profile
            </button>
          )}
        </div>
        <div className="inline-between section-gap">
          <div>
            <h2>Separate dimensions. A fuller picture.</h2>
            <p className="muted">
              Each result opens its formula, inputs and evidence limitations.
            </p>
          </div>
          <button
            className="button secondary"
            onClick={() =>
              setDialog({
                title: "Calculate contribution metrics",
                description:
                  "Snapshots preserve the formula version, evidence inputs and source freshness. Missing or limited evidence suppresses results.",
                fields: [
                  {
                    key: "window_start",
                    label: "Period starts",
                    type: "date",
                    required: true,
                    default: new Date(Date.now() - 90 * 86400000)
                      .toISOString()
                      .slice(0, 10),
                  },
                  {
                    key: "window_end",
                    label: "Period ends",
                    type: "date",
                    required: true,
                    default: today(),
                  },
                  {
                    key: "roadmap",
                    label: "Selected roadmap",
                    type: "relation",
                    options: options("roadmaps"),
                    default: roadmap?.id,
                  },
                ],
                submit: (values) =>
                  action(
                    `employees/${e.id}/calculate/`,
                    values,
                    "Versioned metric snapshots calculated.",
                  ),
                submitLabel: "Calculate snapshots",
              })
            }
          >
            <Icon name="refresh" size={15} />
            Calculate metrics
          </button>
        </div>
        {metricCards(metrics)}
        <div className="tabs">
          {["contributions", "commitments", "skills", "goals", "history"].map(
            (t) => (
              <button
                className={profileTab === t ? "active" : ""}
                key={t}
                onClick={() => setProfileTab(t)}
              >
                {label(t)}
                {t === "contributions" && <span>{ev.length}</span>}
              </button>
            ),
          )}
        </div>
        {profileTab === "contributions" && (
          <Panel
            title="Contribution evidence"
            subtitle="Imported observations, submitted claims and structured assessments"
          >
            {evidenceRows(ev)}
          </Panel>
        )}
        {profileTab === "skills" && (
          <Panel
            title="Skills and assessments"
            subtitle="Self-declared, evidence-supported and reviewer-verified are distinct."
            action={
              <button
                className="button secondary"
                onClick={() => addAssessment(e.id)}
              >
                Add assessment
              </button>
            }
          >
            {assessmentTable(assessments)}
          </Panel>
        )}
        {profileTab === "goals" && (
          <div className="goal-grid">
            {list("goals")
              .filter((g) => g.employee === e.id)
              .map(goalCard)}
            <button className="add-card" onClick={() => addGoal(e.id)}>
              <Icon name="plus" />
              Create a goal
            </button>
          </div>
        )}
        {profileTab === "commitments" && (
          <Panel
            title="Work commitments"
            subtitle="Imported due dates become eligible only after an explicit agreement."
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Work item</th>
                    <th>Commitment</th>
                    <th>Due date</th>
                    <th>Review</th>
                  </tr>
                </thead>
                <tbody>
                  {list("work-items")
                    .filter((w) => ev.some((c) => c.work_item === w.id))
                    .map((w) => (
                      <tr key={w.id}>
                        <td>
                          <strong>{w.title}</strong>
                          <small>
                            {w.category} · {w.status}
                          </small>
                        </td>
                        <td>
                          <Badge
                            state={w.agreed_commitment ? "verified" : "pending"}
                          >
                            {w.agreed_commitment ? "Agreed" : "Not yet agreed"}
                          </Badge>
                        </td>
                        <td>
                          {date(w.due_date)}
                          <small>Original: {date(w.original_due_date)}</small>
                        </td>
                        <td>
                          {canReview && (
                            <button
                              className="text-button"
                              onClick={() =>
                                setDialog({
                                  title: "Agree a delivery commitment",
                                  description:
                                    "Document an agreed date and context. Original commitments and later approved changes are preserved.",
                                  fields: [
                                    {
                                      key: "due_date",
                                      label: "Agreed due date",
                                      type: "date",
                                      required: true,
                                      default: w.due_date ?? today(),
                                    },
                                    {
                                      key: "note",
                                      label:
                                        "Agreement or scope-change context",
                                      type: "textarea",
                                      required: true,
                                    },
                                  ],
                                  submit: (values) =>
                                    action(
                                      `work-items/${w.id}/commit/`,
                                      values,
                                      "Agreed commitment recorded.",
                                    ),
                                  submitLabel: "Record agreement",
                                })
                              }
                            >
                              Record agreement
                            </button>
                          )}
                          {canReview && (
                            <button
                              className="text-button"
                              style={{ marginLeft: 12 }}
                              onClick={() =>
                                setDialog({
                                  title: "Record reviewed quality observations",
                                  description:
                                    "Unknown observations remain unknown. Attribute confirmed defects only with supporting evidence and an independent reviewer.",
                                  fields: [
                                    "accepted",
                                    "reopened",
                                    "rework",
                                    "reviewed_defect",
                                  ]
                                    .map((key): Field => ({
                                      key,
                                      label: label(key),
                                      type: "quality",
                                      options: [
                                        {
                                          value: "true",
                                          label: "Yes — reviewed",
                                        },
                                        {
                                          value: "false",
                                          label: "No — reviewed",
                                        },
                                      ],
                                    }))
                                    .concat([
                                      {
                                        key: "evidence_url",
                                        label: "Quality evidence link",
                                        type: "url",
                                        required: true,
                                      } as Field,
                                    ]),
                                  submit: (values) => {
                                    const result = Object.fromEntries(
                                      Object.entries(values).map(
                                        ([key, value]) => [
                                          key,
                                          key === "evidence_url"
                                            ? value
                                            : value === ""
                                              ? null
                                              : value === "true",
                                        ],
                                      ),
                                    );
                                    return action(
                                      `work-items/${w.id}/quality/`,
                                      result,
                                      "Quality observations recorded.",
                                    );
                                  },
                                  submitLabel: "Record quality review",
                                })
                              }
                            >
                              Review quality
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
        {profileTab === "history" && (
          <Panel
            title="Membership and review history"
            subtitle="Role changes and review decisions remain traceable."
          >
            <div className="timeline">
              {list("memberships")
                .filter((m) => m.employee === e.id)
                .map((m) => (
                  <article key={`m${m.id}`}>
                    <span />
                    <div>
                      <h3>
                        {list("teams").find((t) => t.id === m.team)?.name ??
                          "Team membership"}{" "}
                        ·{" "}
                        {list("roles").find((r) => r.id === m.role)?.name ??
                          "Role"}
                      </h3>
                      <p>
                        {date(m.started_on)} –{" "}
                        {m.ended_on ? date(m.ended_on) : "Present"}
                      </p>
                    </div>
                  </article>
                ))}
              {list("reviews")
                .filter((r) => r.employee === e.id)
                .map((r) => (
                  <article key={`r${r.id}`}>
                    <span />
                    <div>
                      <h3>{r.title}</h3>
                      <p>{r.assessment}</p>
                      <small>{date(r.created_at)}</small>
                    </div>
                  </article>
                ))}
              {list("corrections")
                .filter((c) => c.employee === e.id)
                .map((c) => (
                  <article key={`c${c.id}`}>
                    <span />
                    <div>
                      <h3>Correction · {label(c.status)}</h3>
                      <p>{c.reason}</p>
                      <small>
                        {c.review_note || "Awaiting review"} ·{" "}
                        {date(c.created_at)}
                      </small>
                    </div>
                  </article>
                ))}
            </div>
          </Panel>
        )}
      </>
    );
  }
  function goalCard(g: Entity) {
    return (
      <article className="goal-card" key={g.id}>
        <div className="inline-between">
          <Badge state={g.status}>{label(g.status)}</Badge>
          <span className="muted">{date(g.due_date)}</span>
        </div>
        <h3>{g.title}</h3>
        <p>{g.description || "Success criteria have not been recorded."}</p>
        <div className="progress-label">
          <span>Progress toward goal</span>
          <strong>{g.progress}%</strong>
        </div>
        <Progress value={g.progress} label={`${g.title} progress`} />
        <div className="goal-footer">
          <button
            className="person-cell"
            onClick={() => openEmployee(g.employee)}
          >
            <Avatar name={employeeName(g.employee)} small />
            <span>{employeeName(g.employee)}</span>
          </button>
          <button
            className="text-button"
            onClick={() => addGoal(g.employee, g)}
          >
            Update
            <Icon name="arrow" size={15} />
          </button>
        </div>
      </article>
    );
  }
  function goalsPage() {
    return (
      <>
        <SectionTitle
          eyebrow="GOALS & OUTCOMES"
          title="Connect the work to its purpose."
          text="Track agreed goals and document the outcomes that matter."
          action={
            <button className="button primary" onClick={() => addGoal()}>
              <Icon name="plus" size={17} />
              Create goal
            </button>
          }
        />
        <div className="mini-stats">
          <span>
            <strong>
              {list("goals").filter((g) => g.status === "active").length}
            </strong>
            Active goals
          </span>
          <span>
            <strong>
              {list("goals").filter((g) => g.status === "completed").length}
            </strong>
            Completed goals
          </span>
          <span>
            <strong>{list("outcomes").filter((o) => o.verified).length}</strong>
            Verified outcomes
          </span>
        </div>
        {list("goals").length ? (
          <div className="goal-grid">{list("goals").map(goalCard)}</div>
        ) : (
          <Empty
            title="Start with an agreed goal"
            text="Make intended outcomes visible and connect them to supporting evidence."
            action={
              <button className="button primary" onClick={() => addGoal()}>
                Create goal
              </button>
            }
          />
        )}
        <Panel
          title="Documented business outcomes"
          subtitle="Impact is a reviewed claim supported by evidence."
          action={
            <button className="button secondary" onClick={() => addOutcome()}>
              <Icon name="plus" size={16} />
              Record outcome
            </button>
          }
        >
          {list("outcomes").length ? (
            <div className="outcome-list">
              {list("outcomes").map((o) => (
                <article key={o.id}>
                  <div className="inline-between">
                    <h3>{o.title}</h3>
                    <Badge state={o.verified ? "verified" : "pending"}>
                      {o.verified
                        ? "Verified outcome"
                        : "Awaiting verification"}
                    </Badge>
                  </div>
                  <p>{o.impact}</p>
                  <div className="inline-between">
                    <small>
                      {employeeName(o.employee)} · {date(o.occurred_on)}
                    </small>
                    <div className="inline">
                      <SafeLink href={o.evidence_url}>View evidence</SafeLink>
                      {canReview && !o.verified && (
                        <button
                          className="text-button"
                          onClick={() =>
                            setDialog({
                              title: "Verify business outcome",
                              description:
                                "Confirm that you reviewed the linked evidence and it supports the stated business impact.",
                              children: <p>{o.impact}</p>,
                              submit: () =>
                                action(
                                  `outcomes/${o.id}/verify/`,
                                  {},
                                  "Outcome verification recorded.",
                                ),
                              submitLabel: "Confirm verification",
                            })
                          }
                        >
                          Verify outcome
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              title="Make the impact visible"
              text="Add a customer improvement, delivered capability or risk reduction with evidence."
            />
          )}
        </Panel>
      </>
    );
  }
  function assessmentTable(items: Entity[]) {
    return items.length ? (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Person / skill</th>
              <th>Proficiency</th>
              <th>Evidence basis</th>
              <th>Assessed</th>
              <th>Review</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>
                  <strong>{skillName(a.skill)}</strong>
                  <small>{employeeName(a.employee)}</small>
                </td>
                <td>
                  <span
                    className="level-dots"
                    aria-label={`Level ${a.level} of 5`}
                  >
                    {[1, 2, 3, 4, 5].map((n) => (
                      <i key={n} className={n <= a.level ? "filled" : ""} />
                    ))}
                  </span>
                  <small>{a.level} / 5</small>
                </td>
                <td>
                  <Badge state={a.kind}>{label(a.kind)}</Badge>
                </td>
                <td>
                  {date(a.assessed_on)}
                  <small>
                    {(Date.now() - new Date(a.assessed_on).getTime()) /
                      86400000 >
                    (roadmap?.freshness_days ?? 180)
                      ? "Assessment is stale"
                      : "Within freshness window"}
                  </small>
                </td>
                <td>
                  <div className="inline">
                    <SafeLink href={a.evidence_url}>Evidence</SafeLink>
                    {canReview && a.kind !== "verified" && (
                      <button
                        className="text-button"
                        onClick={() =>
                          setDialog({
                            title: `Verify ${skillName(a.skill)} assessment`,
                            description:
                              "Review the proficiency rubric and evidence. Verification creates a dated review record.",
                            fields: [
                              {
                                key: "note",
                                label: "Reviewer note",
                                type: "textarea",
                                required: true,
                              },
                            ],
                            children: (
                              <p>{a.note || "No assessment note recorded."}</p>
                            ),
                            submit: (values) =>
                              action(
                                `assessments/${a.id}/verify/`,
                                values,
                                "Assessment verified.",
                              ),
                            submitLabel: "Verify assessment",
                          })
                        }
                      >
                        Verify
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <Empty
        title="Skills need evidence"
        text="Record a self-assessment or evidence-supported assessment to start a development conversation."
      />
    );
  }
  function skillsPage() {
    const freshVerified = list("assessments").filter(
      (a) =>
        a.kind === "verified" &&
        (Date.now() - new Date(a.assessed_on).getTime()) / 86400000 <=
          (roadmap?.freshness_days ?? 180),
    );
    return (
      <>
        <SectionTitle
          eyebrow="SKILLS & ROADMAP"
          title="A shared direction for growth."
          text="Compare verified skills with your company’s explicitly defined needs."
          action={
            <button className="button primary" onClick={() => addAssessment()}>
              <Icon name="plus" size={17} />
              Add assessment
            </button>
          }
        />
        <div className="roadmap-selector">
          <div>
            <span className="eyebrow">SELECTED COMPANY ROADMAP</span>
            <h2>{roadmap?.name ?? "No roadmap has been defined"}</h2>
            <p>
              {roadmap?.description ??
                "A roadmap makes future skill requirements explicit and reviewable."}
            </p>
          </div>
          <div>
            {list("roadmaps").length > 0 && (
              <select
                aria-label="Selected roadmap"
                value={roadmap?.id ?? ""}
                onChange={(e) => setRoadmapId(e.target.value)}
              >
                {list("roadmaps").map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            )}
            {systemAdmin && (
              <button
                className="text-button"
                onClick={() =>
                  create("roadmaps", "Create a skills roadmap", [
                    { key: "name", label: "Roadmap name", required: true },
                    {
                      key: "description",
                      label: "Business context",
                      type: "textarea",
                      required: true,
                    },
                    {
                      key: "target_date",
                      label: "Target date",
                      type: "date",
                      required: true,
                    },
                    {
                      key: "target_role",
                      label: "Target role",
                      type: "relation",
                      options: options("roles"),
                    },
                    {
                      key: "minimum_coverage",
                      label: "Required assessment coverage (0.5–1)",
                      type: "number",
                      min: 0.5,
                      max: 1,
                      step: 0.05,
                      default: 1,
                    },
                    {
                      key: "freshness_days",
                      label: "Assessment freshness (days)",
                      type: "number",
                      min: 1,
                      max: 730,
                      default: 180,
                    },
                  ])
                }
              >
                Create roadmap
                <Icon name="plus" size={14} />
              </button>
            )}
          </div>
        </div>
        <div className="notice">
          <Icon name="info" />
          <span>
            Alignment is specific to this roadmap. Results require{" "}
            {Math.round((roadmap?.minimum_coverage ?? 1) * 100)}% assessment
            coverage and evidence within {roadmap?.freshness_days ?? 180} days.
            Unknown skills remain unassessed.
          </span>
        </div>
        <Panel
          title="Verified skills matrix"
          subtitle={
            roadmap
              ? `Target ${date(roadmap.target_date)} · Roadmap version ${roadmap.version}`
              : "Select or define a roadmap to see required skills"
          }
          action={
            systemAdmin && roadmap ? (
              <button
                className="button secondary"
                onClick={() =>
                  create("requirements", "Add a roadmap requirement", [
                    {
                      key: "roadmap",
                      label: "Roadmap",
                      type: "relation",
                      options: options("roadmaps"),
                      default: roadmap.id,
                      required: true,
                    },
                    {
                      key: "skill",
                      label: "Required skill",
                      type: "relation",
                      options: options("skills"),
                      required: true,
                    },
                    {
                      key: "required_level",
                      label: "Target proficiency (1–5)",
                      type: "number",
                      min: 1,
                      max: 5,
                      default: 3,
                      required: true,
                    },
                    {
                      key: "weight",
                      label: "Importance weight",
                      type: "number",
                      min: 0.01,
                      max: 100,
                      step: 0.1,
                      default: 1,
                      required: true,
                    },
                    {
                      key: "development_action",
                      label: "Development action",
                      type: "textarea",
                      required: true,
                    },
                  ])
                }
              >
                Add requirement
              </button>
            ) : undefined
          }
        >
          {requirements.length ? (
            <div className="table-scroll">
              <table className="matrix">
                <thead>
                  <tr>
                    <th>Employee</th>
                    {requirements.map((r) => (
                      <th key={r.id}>
                        {skillName(r.skill)}
                        <small>Target level {r.required_level}</small>
                      </th>
                    ))}
                    <th>Assessment coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {list("employees").map((e) => {
                    const assessed = requirements.filter((r) =>
                      freshVerified.some(
                        (a) => a.employee === e.id && a.skill === r.skill,
                      ),
                    ).length;
                    return (
                      <tr key={e.id}>
                        <td>
                          <button
                            className="person-cell"
                            onClick={() => openEmployee(e.id)}
                          >
                            <Avatar name={e.name} small />
                            {e.name}
                          </button>
                        </td>
                        {requirements.map((r) => {
                          const a = freshVerified
                            .filter(
                              (a) => a.employee === e.id && a.skill === r.skill,
                            )
                            .sort((a, b) =>
                              String(b.assessed_on).localeCompare(
                                String(a.assessed_on),
                              ),
                            )[0];
                          return (
                            <td key={r.id}>
                              <span
                                className={`matrix-value ${!a ? "unknown" : a.level >= r.required_level ? "met" : "gap"}`}
                              >
                                {a ? `${a.level} / ${r.required_level}` : "—"}
                              </span>
                              <small>
                                {!a
                                  ? "Not assessed"
                                  : a.level >= r.required_level
                                    ? "Target met"
                                    : "Development gap"}
                              </small>
                            </td>
                          );
                        })}
                        <td>
                          <strong>
                            {Math.round((100 * assessed) / requirements.length)}
                            %
                          </strong>
                          <small>
                            {assessed} of {requirements.length} skills verified
                          </small>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="Define the required skills"
              text="Add skill requirements, target proficiency and development actions to this roadmap."
            />
          )}
          <div className="panel-note">
            <Icon name="info" size={15} />
            Only fresh, reviewer-verified assessments appear in this matrix.
          </div>
        </Panel>
        {requirements.length > 0 && (
          <div className="development-grid">
            {requirements.map((r) => (
              <article key={r.id}>
                <span className="eyebrow">DEVELOPMENT OPPORTUNITY</span>
                <h3>{skillName(r.skill)}</h3>
                <p>
                  {r.development_action ||
                    "Agree a development action with the employee."}
                </p>
                <small>
                  Target level {r.required_level} · Importance weight {r.weight}
                </small>
              </article>
            ))}
          </div>
        )}
        <Panel
          title="Assessment history"
          subtitle="Every basis and assessment date remains visible."
          action={
            systemAdmin ? (
              <button
                className="text-button"
                onClick={() =>
                  create("skills", "Add a skill", [
                    { key: "name", label: "Skill name", required: true },
                    {
                      key: "category",
                      label: "Category",
                      default: "Engineering",
                      required: true,
                    },
                    {
                      key: "description",
                      label: "Description",
                      type: "textarea",
                    },
                    {
                      key: "rubric",
                      label: "Proficiency rubric (JSON)",
                      type: "json",
                      default: JSON.stringify(
                        {
                          "1": "Foundational",
                          "2": "Developing",
                          "3": "Independent",
                          "4": "Advanced",
                          "5": "Expert",
                        },
                        null,
                        2,
                      ),
                      required: true,
                    },
                  ])
                }
              >
                Manage taxonomy
                <Icon name="plus" size={14} />
              </button>
            ) : undefined
          }
        >
          {assessmentTable(list("assessments"))}
        </Panel>
        <Panel
          title="Skill taxonomy and proficiency rubrics"
          subtitle="Use these published definitions when creating and verifying assessments."
        >
          <div className="definition-list" style={{ padding: "0 22px" }}>
            {list("skills").map((skill) => (
              <details key={skill.id}>
                <summary>
                  <span className="definition-icon">
                    <Icon name="skills" />
                  </span>
                  <span>
                    <strong>{skill.name}</strong>
                    <small>
                      {skill.category} · {skill.description}
                    </small>
                  </span>
                  <Icon name="chevron" size={16} />
                </summary>
                <div className="definition-body">
                  <dl>
                    {Object.entries(skill.rubric ?? {}).map(
                      ([level, definition]) => (
                        <div key={level} style={{ display: "contents" }}>
                          <dt>Level {level}</dt>
                          <dd>{String(definition)}</dd>
                        </div>
                      ),
                    )}
                  </dl>
                  <p className="muted">
                    Candidate evidence rules identify material to review; they
                    do not establish proficiency.
                  </p>
                  <pre>{JSON.stringify(skill.candidate_rules, null, 2)}</pre>
                </div>
              </details>
            ))}
          </div>
        </Panel>
      </>
    );
  }
  function reviewsPage() {
    return (
      <>
        <SectionTitle
          eyebrow="REVIEWS & CORRECTIONS"
          title="Make room for the whole story."
          text="Review evidence, add missing context and keep decisions traceable."
          action={
            canReview ? (
              <button
                className="button primary"
                onClick={() =>
                  create(
                    "reviews",
                    "Record a structured review",
                    [
                      employeeField(),
                      { key: "title", label: "Review title", required: true },
                      {
                        key: "assessment",
                        label: "Structured assessment and evidence",
                        type: "textarea",
                        required: true,
                      },
                    ],
                    "Describe the observed contribution, evidence and development actions. Avoid unsupported conclusions.",
                  )
                }
              >
                Record review
                <Icon name="plus" size={16} />
              </button>
            ) : (
              <button
                className="button primary"
                onClick={() => addCorrection()}
              >
                Request correction
                <Icon name="plus" size={16} />
              </button>
            )
          }
        />
        <div className="tabs">
          {[
            {
              key: "corrections",
              name: "Correction requests",
              count: pending.length,
            },
            {
              key: "evidence",
              name: "Evidence verification",
              count: list("contributions").filter((c) => !c.verified).length,
            },
            {
              key: "assessments",
              name: "Skill assessments",
              count: list("assessments").filter((a) => a.kind !== "verified")
                .length,
            },
            {
              key: "reviews",
              name: "Review history",
              count: list("reviews").length,
            },
          ].map((t) => (
            <button
              className={reviewTab === t.key ? "active" : ""}
              key={t.key}
              onClick={() => setReviewTab(t.key)}
            >
              {t.name}
              <span>{t.count}</span>
            </button>
          ))}
        </div>
        {reviewTab === "corrections" && (
          <Panel
            title="Correction requests"
            subtitle="Approved context is added with an immutable review trail."
            action={
              <button
                className="button secondary"
                onClick={() => addCorrection()}
              >
                New request
              </button>
            }
          >
            {list("corrections").length ? (
              <div className="review-list">
                {list("corrections").map((c) => (
                  <article key={c.id}>
                    <div className="inline-between">
                      <div className="person-cell">
                        <Avatar name={employeeName(c.employee)} small />
                        <strong>{employeeName(c.employee)}</strong>
                        <small>{date(c.created_at)}</small>
                      </div>
                      <Badge state={c.status}>{label(c.status)}</Badge>
                    </div>
                    <h3>{c.reason}</h3>
                    <blockquote>{c.requested_context}</blockquote>
                    {c.review_note && (
                      <p className="review-note">
                        <strong>Review note:</strong> {c.review_note}
                      </p>
                    )}
                    {canReview && c.status === "pending" && (
                      <button
                        className="button secondary"
                        onClick={() =>
                          setDialog({
                            title: "Review correction request",
                            description:
                              "A decision is recorded with the original and updated context. You cannot review your own request.",
                            children: (
                              <>
                                <h3>{c.reason}</h3>
                                <blockquote>{c.requested_context}</blockquote>
                              </>
                            ),
                            fields: [
                              {
                                key: "decision",
                                label: "Decision",
                                required: true,
                                options: [
                                  {
                                    value: "approved",
                                    label: "Approve correction",
                                  },
                                  {
                                    value: "rejected",
                                    label: "Reject with explanation",
                                  },
                                ],
                              },
                              {
                                key: "review_note",
                                label: "Review explanation",
                                type: "textarea",
                                required: true,
                              },
                            ],
                            submit: (values) =>
                              action(
                                `corrections/${c.id}/review/`,
                                values,
                                "Correction decision recorded.",
                              ),
                            submitLabel: "Record decision",
                          })
                        }
                      >
                        Review request
                        <Icon name="arrow" size={15} />
                      </button>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title="No correction requests"
                text="Employees can request corrections from any contribution or their profile."
              />
            )}
          </Panel>
        )}
        {reviewTab === "evidence" && (
          <Panel
            title="Contribution verification"
            subtitle="Read the source evidence before confirming a claim."
          >
            {list("contributions").filter((c) => !c.verified).length ? (
              <div className="review-list">
                {list("contributions")
                  .filter((c) => !c.verified)
                  .map((c) => (
                    <article key={c.id}>
                      <div className="inline-between">
                        <h3>{c.title}</h3>
                        <Badge state={c.origin}>{label(c.origin)}</Badge>
                      </div>
                      <p>{c.context || "No context has been provided."}</p>
                      <div className="inline-between">
                        <span className="muted">
                          {employeeName(c.employee)} · {date(c.occurred_on)}
                        </span>
                        <div className="inline">
                          <SafeLink href={c.evidence_url}>
                            Source evidence
                          </SafeLink>
                          {canReview && (
                            <button
                              className="button secondary"
                              onClick={() =>
                                setDialog({
                                  title: "Verify contribution",
                                  description:
                                    "Confirm that you have reviewed the linked evidence and the employee’s contribution context.",
                                  children: <p>{c.title}</p>,
                                  submit: () =>
                                    action(
                                      `contributions/${c.id}/verify/`,
                                      {},
                                      "Contribution verification recorded.",
                                    ),
                                  submitLabel: "Verify contribution",
                                })
                              }
                            >
                              Verify
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  ))}
              </div>
            ) : (
              <Empty
                title="Evidence reviews are up to date"
                text="New unverified contributions will appear here."
              />
            )}
          </Panel>
        )}
        {reviewTab === "assessments" && (
          <Panel
            title="Skill assessment review"
            subtitle="Verify proficiency using the documented rubric and linked evidence."
          >
            {assessmentTable(list("assessments"))}
          </Panel>
        )}
        {reviewTab === "reviews" && (
          <Panel title="Structured review history">
            {list("reviews").length ? (
              <div className="review-list">
                {list("reviews").map((r) => (
                  <article key={r.id}>
                    <div className="inline-between">
                      <h3>{r.title}</h3>
                      <small>{date(r.created_at)}</small>
                    </div>
                    <p>{r.assessment}</p>
                    <small>
                      {employeeName(r.employee)} · Reviewer #{r.reviewer}
                    </small>
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title="No structured reviews yet"
                text="Reviewers can document observations, evidence and development actions."
              />
            )}
          </Panel>
        )}
      </>
    );
  }
  async function sourceAction(source: Entity, kind: "test" | "sync") {
    try {
      const result = await action(
        `sources/${source.id}/${kind}/`,
        {},
        kind === "sync"
          ? "Synchronization queued. Refresh to see worker progress."
          : "Connection diagnostics completed.",
      );
      if (kind === "test")
        setDialog({
          title: `${source.name} · connection diagnostics`,
          children: <pre>{JSON.stringify(result, null, 2)}</pre>,
        });
    } catch {
      /* The action helper displays the error. */
    }
  }
  function sourcesPage() {
    const unresolved = list("identities").filter((i) =>
      ["unresolved", "ambiguous"].includes(i.status),
    );
    return (
      <>
        <SectionTitle
          eyebrow="DATA SOURCES & IDENTITY"
          title="Evidence with a clear origin."
          text="Connect approved work systems, inspect freshness and resolve identity matches."
          action={
            <button className="button primary" onClick={() => addSource()}>
              <Icon name="plus" size={17} />
              Connect source
            </button>
          }
        />
        <div className="notice">
          <Icon name="administration" />
          <span>
            Source credentials grant only configured source access. Employee
            visibility is governed separately by WorkLens roles and reporting
            scope.
          </span>
        </div>
        <div className="source-grid">
          {list("sources").map((s) => {
            const runs = list("sync-runs")
              .filter((r) => r.source === s.id)
              .sort((a, b) => b.id - a.id);
            const stale =
              !s.last_success_at ||
              (Date.now() - new Date(s.last_success_at).getTime()) / 86400000 >
                2;
            return (
              <article className="source-card" key={s.id}>
                <div className="inline-between">
                  <span className={`source-logo ${s.kind}`}>
                    {s.kind === "jira"
                      ? "J"
                      : s.kind === "bitbucket"
                        ? "B"
                        : s.kind === "confluence"
                          ? "C"
                          : "W"}
                  </span>
                  <Badge
                    state={!s.enabled ? "disabled" : stale ? "stale" : "fresh"}
                  >
                    {!s.enabled ? "Disabled" : stale ? "Needs sync" : "Current"}
                  </Badge>
                </div>
                <h3>{s.name}</h3>
                <p>
                  {label(s.kind)} · {label(s.deployment)}
                </p>
                <dl>
                  <dt>Last successful sync</dt>
                  <dd>{when(s.last_success_at)}</dd>
                  <dt>Access scopes</dt>
                  <dd>
                    {s.scopes.length
                      ? s.scopes.join(", ")
                      : s.kind === "fixture"
                        ? "Local synthetic fixture"
                        : "Not configured"}
                  </dd>
                  <dt>Latest sync</dt>
                  <dd>
                    {runs[0]
                      ? `${label(runs[0].status)} · ${runs[0].records_processed} records`
                      : "No sync runs"}
                  </dd>
                </dl>
                <div className="source-actions">
                  <button
                    className="button secondary"
                    onClick={() => sourceAction(s, "test")}
                  >
                    Test connection
                  </button>
                  <button
                    className="button primary"
                    onClick={() => sourceAction(s, "sync")}
                    disabled={!s.enabled}
                  >
                    <Icon name="refresh" size={15} />
                    Sync
                  </button>
                  <button className="text-button" onClick={() => addSource(s)}>
                    Configure
                  </button>
                  <button
                    className="text-button"
                    onClick={() =>
                      setDialog({
                        title: "Reconcile source access",
                        description:
                          "A full scan quarantines records that are no longer available in approved scopes. Run this after permissions or source allowlists change.",
                        submit: () =>
                          action(
                            `sources/${s.id}/reconcile/`,
                            {},
                            "Source reconciliation queued.",
                          ),
                        submitLabel: "Start reconciliation",
                      })
                    }
                  >
                    Reconcile access
                  </button>
                </div>
                <div className="source-retention">
                  <span>{s.retention_days} day retention</span>
                  <button
                    onClick={() =>
                      setDialog({
                        title: `Remove retained data from ${s.name}?`,
                        description:
                          "This permanently removes retained imported records and associated evidence for this source. Disabling the source first prevents new synchronization. This action is audited.",
                        danger: true,
                        fields: [
                          {
                            key: "confirm",
                            label:
                              "Confirm permanent removal of retained source data",
                            type: "checkbox",
                            required: true,
                          },
                        ],
                        submit: (values) => {
                          if (!values.confirm)
                            throw new Error("Confirm removal to continue.");
                          return action(
                            `sources/${s.id}/purge/`,
                            { confirm: true },
                            "Retained source data removed.",
                          );
                        },
                        submitLabel: "Remove retained data",
                      })
                    }
                  >
                    Remove data
                  </button>
                </div>
              </article>
            );
          })}
          <button className="add-source" onClick={() => addSource()}>
            <span>
              <Icon name="plus" size={26} />
            </span>
            <h3>Add an approved source</h3>
            <p>
              Jira, Bitbucket, Confluence
              <br />
              or a local synthetic fixture
            </p>
          </button>
        </div>
        <Panel
          title="Identity review"
          subtitle="Stable employee IDs link evidence. Ambiguous matches require an explicit decision."
          action={<span className="pill">{unresolved.length} need review</span>}
        >
          {list("identities").length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source account</th>
                    <th>Source</th>
                    <th>Employee</th>
                    <th>Match status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {list("identities").map((i) => (
                    <tr key={i.id}>
                      <td>
                        <strong>{i.account_id}</strong>
                        <small>{i.email || "No email supplied"}</small>
                      </td>
                      <td>{sourceName(i.source)}</td>
                      <td>
                        {i.employee ? employeeName(i.employee) : "Unassigned"}
                      </td>
                      <td>
                        <Badge state={i.status}>{label(i.status)}</Badge>
                      </td>
                      <td>
                        {["unresolved", "ambiguous"].includes(i.status) ? (
                          <button
                            className="text-button"
                            onClick={() =>
                              setDialog({
                                title: "Resolve source identity",
                                description: `Map ${i.account_id} (${i.email || "no email"}) to a stable employee. Email is a matching attribute, never an authorization grant.`,
                                fields: [
                                  {
                                    key: "employee",
                                    label: "Employee",
                                    type: "relation",
                                    options: options("employees"),
                                  },
                                  {
                                    key: "service",
                                    label:
                                      "This is a service account; do not attribute it to a person",
                                    type: "checkbox",
                                  },
                                ],
                                submit: (values) => {
                                  if (!values.service && !values.employee)
                                    throw new Error(
                                      "Select an employee or classify the identity as a service account.",
                                    );
                                  return action(
                                    `identities/${i.id}/resolve/`,
                                    values,
                                    "Identity resolution recorded.",
                                  );
                                },
                                submitLabel: "Resolve identity",
                              })
                            }
                          >
                            Resolve match
                            <Icon name="arrow" size={14} />
                          </button>
                        ) : (
                          <span className="muted">Reviewed</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No source identities yet"
              text="Run a synchronization to discover identities from allowed source records."
            />
          )}
        </Panel>
        <Panel
          title="Synchronization history"
          subtitle="Worker progress, coverage and permission diagnostics"
          action={
            <button className="text-button" onClick={() => void refresh()}>
              <Icon name="refresh" size={14} />
              Refresh status
            </button>
          }
        >
          {list("sync-runs").length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Started</th>
                    <th>Records</th>
                    <th>Diagnostics</th>
                  </tr>
                </thead>
                <tbody>
                  {[...list("sync-runs")]
                    .sort((a, b) => b.id - a.id)
                    .slice(0, 25)
                    .map((r) => (
                      <tr key={r.id}>
                        <td>{sourceName(r.source)}</td>
                        <td>
                          <Badge state={r.status}>{label(r.status)}</Badge>
                        </td>
                        <td>{when(r.started_at)}</td>
                        <td>{r.records_processed}</td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() =>
                              setDialog({
                                title: `Sync run #${r.id}`,
                                children: (
                                  <pre>
                                    {JSON.stringify(
                                      {
                                        status: r.status,
                                        error: r.error,
                                        diagnostics: r.diagnostics,
                                        cursor: r.cursor,
                                      },
                                      null,
                                      2,
                                    )}
                                  </pre>
                                ),
                              })
                            }
                          >
                            {r.error ? "Review error" : "Inspect run"}
                            <Icon name="arrow" size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No synchronization runs yet"
              text="Connection tests check permissions; synchronization imports allowed records."
            />
          )}
        </Panel>
        <Panel
          title="CSV import"
          subtitle="Import structured records using locally prepared CSV files"
        >
          <div className="csv-section">
            <Icon name="reports" size={34} />
            <div>
              <h3>Bring your existing records into WorkLens</h3>
              <p>
                Employee directory, organization structure, skills, goals,
                assessments and historical evidence. Imports are validated and
                audited.
              </p>
            </div>
            <button
              className="button secondary"
              disabled={!systemAdmin}
              onClick={() =>
                setDialog({
                  title: "Import structured CSV records",
                  description:
                    "Use numeric IDs for relationships; employee fields may also use stable employee IDs. All records are validated before import.",
                  fields: [
                    {
                      key: "kind",
                      label: "Record type",
                      required: true,
                      default: "employees",
                      options: [
                        "employees",
                        "teams",
                        "roles",
                        "skills",
                        "goals",
                        "assessments",
                        "historical_records",
                        "memberships",
                      ].map((v) => ({ value: v, label: label(v) })),
                    },
                    {
                      key: "content",
                      label: "CSV content, including header row",
                      type: "textarea",
                      required: true,
                      hint: "Employee example: stable_id,name,email,team,role,manager. Skill example: name,category,description.",
                    },
                  ],
                  submit: (values) =>
                    action("csv-import/", values, "CSV records imported."),
                  submitLabel: "Validate and import",
                })
              }
            >
              Import CSV
              <Icon name="arrow" size={15} />
            </button>
          </div>
        </Panel>
        <Panel
          title="Source visibility scopes"
          subtitle="Limit source content to approved team scopes."
          action={
            <button
              className="button secondary"
              onClick={() =>
                create("access-scopes", "Grant a team source scope", [
                  {
                    key: "source",
                    label: "Source",
                    type: "relation",
                    options: options("sources"),
                    required: true,
                  },
                  {
                    key: "scope",
                    label: "Project, repository or space key",
                    required: true,
                  },
                  {
                    key: "team",
                    label: "Authorized team",
                    type: "relation",
                    options: options("teams"),
                    required: true,
                  },
                ])
              }
            >
              Add scope
            </button>
          }
        >
          {list("access-scopes").length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Scope</th>
                    <th>Authorized team</th>
                  </tr>
                </thead>
                <tbody>
                  {list("access-scopes").map((s) => (
                    <tr key={s.id}>
                      <td>{sourceName(s.source)}</td>
                      <td>{s.scope}</td>
                      <td>
                        {list("teams").find((t) => t.id === s.team)?.name ??
                          "Unassigned"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No team visibility scopes"
              text="Configure source scopes deliberately before broadening visibility."
            />
          )}
        </Panel>
      </>
    );
  }
  function metricsPage() {
    return (
      <>
        <SectionTitle
          eyebrow="METRIC DICTIONARY"
          title="Every number has a definition."
          text="Transparent, versioned calculations. Explicit assumptions. Evidence you can inspect."
        />
        <div className="principle-grid">
          <article>
            <Icon name="reports" />
            <h3>Evidence before conclusions</h3>
            <p>
              Missing data stays unknown. Minimum sample and freshness
              requirements suppress unsupported results.
            </p>
          </article>
          <article>
            <Icon name="people" />
            <h3>Context belongs in the picture</h3>
            <p>
              Work category, shared contributions, capacity, dependencies and
              role changes accompany the evidence.
            </p>
          </article>
          <article>
            <Icon name="administration" />
            <h3>People make the decisions</h3>
            <p>
              WorkLens supports review and development. It does not automate
              employment or compensation decisions.
            </p>
          </article>
        </div>
        {list("metric-definitions").length ? (
          <div className="definition-list">
            {list("metric-definitions").map((d) => (
              <details key={d.id}>
                <summary>
                  <span className="definition-icon">
                    <Icon name="metrics" />
                  </span>
                  <span>
                    <strong>{d.name}</strong>
                    <small>{d.definition}</small>
                  </span>
                  <span className="pill">v{d.version}</span>
                  <Icon name="chevron" size={17} />
                </summary>
                <div className="definition-body">
                  <dl>
                    <dt>Intended use</dt>
                    <dd>{d.intended_use}</dd>
                    <dt>Formula</dt>
                    <dd>
                      <code>{d.formula}</code>
                    </dd>
                    <dt>Configuration</dt>
                    <dd>
                      <pre>{JSON.stringify(d.config, null, 2)}</pre>
                    </dd>
                    <dt>Version created</dt>
                    <dd>{when(d.created_at)}</dd>
                  </dl>
                </div>
              </details>
            ))}
          </div>
        ) : (
          <Empty
            title="No metric definitions installed"
            text="Ask your administrator to initialize the versioned metric dictionary."
          />
        )}
        <div className="notice">
          <Icon name="info" />
          <span>
            Workflow time describes a process, not hours worked. Activity counts
            are never treated as contribution quality, and unrelated roles are
            not ranked.
          </span>
        </div>
      </>
    );
  }
  function reportsPage() {
    return (
      <>
        <SectionTitle
          eyebrow="REPORTS & EXPORTS"
          title="Take the evidence into the conversation."
          text="Create authorized reports with evidence context and versioned calculation details."
        />
        <div className="report-grid">
          <article className="report-intro">
            <span className="eyebrow">CONTRIBUTION REPORT</span>
            <div className="report-art" aria-hidden="true">
              <Icon name="reports" size={74} />
              <span>
                <Icon name="check" size={24} />
              </span>
            </div>
            <h2>
              Traceable. Reviewable.
              <br />
              Ready for a conversation.
            </h2>
            <p>
              Exports contain only records your role is authorized to access.
              Each export is recorded in the audit trail.
            </p>
            <div className="inline">
              <Badge state="verified">Role-scoped access</Badge>
              <Badge>CSV / PDF</Badge>
            </div>
          </article>
          <Panel
            title="Create an employee report"
            subtitle="Select a person in your authorized scope."
          >
            <form
              className="report-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                const person = form.get("employee");
                const format = form.get("format");
                const mode = (
                  e.nativeEvent as SubmitEvent
                ).submitter?.getAttribute("value");
                if (mode === "queue") {
                  try {
                    await action(
                      "report-jobs/",
                      { employee: Number(person), format },
                      "Report queued. Your worker will generate an authorized report.",
                    );
                  } catch {
                    /* Error is shown by action. */
                  }
                  return;
                }
                try {
                  const res = await fetch(
                    `/api/reports/export/?employee=${encodeURIComponent(String(person))}&format=${encodeURIComponent(String(format))}`,
                    { credentials: "same-origin" },
                  );
                  if (!res.ok) {
                    const result = await res.json().catch(() => ({}));
                    throw new Error(
                      result.detail ?? `Export failed (${res.status}).`,
                    );
                  }
                  const url = URL.createObjectURL(await res.blob());
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `worklens-employee-${person}.${format}`;
                  a.click();
                  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                  notify("Authorized report exported.");
                } catch (e) {
                  notify((e as Error).message);
                }
              }}
            >
              <label className="field">
                <span>Employee</span>
                <select
                  aria-label="Employee"
                  name="employee"
                  required
                  defaultValue={session?.employee_id ?? ""}
                >
                  <option value="">Select an employee</option>
                  {options("employees").map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <fieldset>
                <legend>Export format</legend>
                <label className="radio-card">
                  <input
                    aria-label="PDF report"
                    type="radio"
                    name="format"
                    value="pdf"
                    defaultChecked
                  />
                  <span>
                    <strong>PDF report</strong>
                    <small>Readable evidence and calculation summary</small>
                  </span>
                  <Icon name="reports" />
                </label>
                <label className="radio-card">
                  <input
                    aria-label="CSV data"
                    type="radio"
                    name="format"
                    value="csv"
                  />
                  <span>
                    <strong>CSV data</strong>
                    <small>Structured records for internal analysis</small>
                  </span>
                  <Icon name="sources" />
                </label>
              </fieldset>
              <div className="notice compact">
                <Icon name="info" size={18} />
                <span>
                  Store exported employee data according to your company’s
                  access and retention policies.
                </span>
              </div>
              <div className="inline">
                <button type="submit" className="button primary">
                  <Icon name="download" size={17} />
                  Export report
                </button>
                <button
                  type="submit"
                  name="mode"
                  value="queue"
                  className="button secondary"
                >
                  <Icon name="clock" size={17} />
                  Queue report
                </button>
              </div>
            </form>
          </Panel>
        </div>
        <Panel
          title="Background report jobs"
          subtitle="Generated on your infrastructure. Downloads expire after 24 hours and recheck access."
          action={
            <button
              className="text-button"
              onClick={() => void refresh(["report-jobs"])}
            >
              Refresh jobs
              <Icon name="refresh" size={14} />
            </button>
          }
        >
          {list("report-jobs").length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Format</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Download</th>
                  </tr>
                </thead>
                <tbody>
                  {[...list("report-jobs")]
                    .sort((a, b) => b.id - a.id)
                    .map((job) => (
                      <tr key={job.id} data-report-id={job.id}>
                        <td>{employeeName(job.employee)}</td>
                        <td>{String(job.format).toUpperCase()}</td>
                        <td>
                          <Badge state={job.status}>{label(job.status)}</Badge>
                          {job.error && <small>{job.error}</small>}
                        </td>
                        <td>{when(job.created_at)}</td>
                        <td>
                          {job.status === "succeeded" ? (
                            <a
                              href={`/api/report-jobs/${job.id}/download/`}
                              download
                            >
                              Download report
                              <Icon name="download" size={14} />
                            </a>
                          ) : (
                            <small>
                              {job.status === "queued"
                                ? "Waiting for worker"
                                : "Not available"}
                            </small>
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No background reports yet"
              text="Queue a report to generate it in the background, then refresh its status."
            />
          )}
        </Panel>
      </>
    );
  }
  function administrationPage() {
    return (
      <>
        <SectionTitle
          eyebrow="ADMINISTRATION"
          title="A deliberate, accountable workspace."
          text="Manage organization structure, access responsibilities and the data lifecycle."
        />
        <div className="admin-grid">
          <Panel
            title="Organization structure"
            subtitle="Teams and role templates define the work context."
          >
            <div className="admin-actions">
              <button
                onClick={() =>
                  create("teams", "Create a team", [
                    { key: "name", label: "Team name", required: true },
                    {
                      key: "description",
                      label: "Team purpose",
                      type: "textarea",
                    },
                  ])
                }
              >
                <Icon name="people" />
                <span>
                  <strong>Teams</strong>
                  <small>{list("teams").length} configured teams</small>
                </span>
                <Icon name="plus" size={17} />
              </button>
              <button
                onClick={() =>
                  create("roles", "Create a role template", [
                    { key: "name", label: "Role name", required: true },
                    {
                      key: "description",
                      label: "Role expectations",
                      type: "textarea",
                    },
                    {
                      key: "work_categories",
                      label: "Comparable work categories",
                      type: "list",
                      hint: "Comma-separated categories; compare like work within the role.",
                    },
                  ])
                }
              >
                <Icon name="reviews" />
                <span>
                  <strong>Role templates</strong>
                  <small>{list("roles").length} configured roles</small>
                </span>
                <Icon name="plus" size={17} />
              </button>
              <button onClick={() => addEmployee()}>
                <Icon name="people" />
                <span>
                  <strong>Employee directory</strong>
                  <small>Add an employee and access responsibility</small>
                </span>
                <Icon name="plus" size={17} />
              </button>
              <button
                onClick={() =>
                  setDialog({
                    title: "Provision a local account",
                    description:
                      "Create or reset an employee login. Share temporary credentials using your approved internal process. Existing usernames cannot be changed.",
                    fields: [
                      employeeField(),
                      { key: "username", label: "Username", required: true },
                      {
                        key: "password",
                        label: "New password",
                        type: "password",
                        required: true,
                        hint: "At least 12 characters. Do not reuse passwords from another account.",
                      },
                    ],
                    submit: (values) =>
                      action(
                        `employees/${values.employee}/account/`,
                        {
                          username: values.username,
                          password: values.password,
                        },
                        "Local account provisioned.",
                      ),
                    submitLabel: "Provision account",
                  })
                }
              >
                <Icon name="administration" />
                <span>
                  <strong>Local accounts</strong>
                  <small>Create or reset employee sign-in credentials</small>
                </span>
                <Icon name="plus" size={17} />
              </button>
              <button
                onClick={() =>
                  create("memberships", "Record a team membership", [
                    employeeField(),
                    {
                      key: "team",
                      label: "Team",
                      type: "relation",
                      options: options("teams"),
                      required: true,
                    },
                    {
                      key: "role",
                      label: "Role",
                      type: "relation",
                      options: options("roles"),
                    },
                    {
                      key: "started_on",
                      label: "Started on",
                      type: "date",
                      required: true,
                      default: today(),
                    },
                    { key: "ended_on", label: "Ended on", type: "date" },
                  ])
                }
              >
                <Icon name="clock" />
                <span>
                  <strong>Membership history</strong>
                  <small>Preserve team and role changes</small>
                </span>
                <Icon name="plus" size={17} />
              </button>
            </div>
          </Panel>
          <Panel
            title="Data lifecycle"
            subtitle="Explicit retention and offboarding actions."
          >
            <div className="retention-content">
              <span className="attention-symbol amber">
                <Icon name="administration" size={26} />
              </span>
              <h3>Keep only what is needed.</h3>
              <p>
                Review the retention preview before applying deletion. Backup
                retention is managed separately in your deployment policy.
              </p>
              <button
                className="button secondary"
                onClick={async () => {
                  try {
                    const preview = await api("retention/");
                    setDialog({
                      title: "Apply retention policy",
                      description:
                        "This deletes eligible retained records using each source’s retention period. Inspect the preview before confirming. Audit history is preserved.",
                      children: <pre>{JSON.stringify(preview, null, 2)}</pre>,
                      fields: [
                        {
                          key: "confirm",
                          label: "Apply the retention deletion shown above",
                          type: "checkbox",
                          required: true,
                        },
                      ],
                      submit: (values) => {
                        if (!values.confirm)
                          throw new Error(
                            "Confirm the retention deletion to continue.",
                          );
                        return action(
                          "retention/",
                          { confirm: true },
                          "Retention policy applied.",
                        );
                      },
                      submitLabel: "Apply retention",
                      danger: true,
                    });
                  } catch (e) {
                    notify((e as Error).message);
                  }
                }}
              >
                Preview retention
                <Icon name="arrow" size={15} />
              </button>
              <button
                className="text-button"
                onClick={() =>
                  setDialog({
                    title: "Offboard an employee",
                    description:
                      "This disables employee access and stops active identity attribution. Historical records remain subject to retention and deletion policy.",
                    fields: [
                      employeeField(),
                      {
                        key: "confirm",
                        label: "Confirm employee offboarding",
                        type: "checkbox",
                        required: true,
                      },
                    ],
                    submit: (values) => {
                      if (!values.confirm)
                        throw new Error("Confirm offboarding to continue.");
                      return action(
                        `employees/${values.employee}/offboard/`,
                        { confirm: true },
                        "Employee offboarded.",
                      );
                    },
                    submitLabel: "Offboard employee",
                    danger: true,
                  })
                }
              >
                Employee offboarding
                <Icon name="arrow" size={15} />
              </button>
            </div>
          </Panel>
        </div>
        <Panel
          title="Access responsibilities"
          subtitle="Authorization is enforced on every API record and export."
        >
          <div className="access-grid">
            {[
              {
                role: "Employee",
                text: "Own evidence, assessments, goals and correction requests.",
              },
              {
                role: "Manager",
                text: "Authorized reporting scope and review workflows.",
              },
              {
                role: "Reviewer",
                text: "Structured assessment and evidence review responsibilities.",
              },
              {
                role: "Integration administrator",
                text: "Source configuration, diagnostics and identity resolution.",
              },
              {
                role: "System administrator",
                text: "Organization, access roles, retention and audit administration.",
              },
            ].map((r) => (
              <article key={r.role}>
                <Icon name="administration" size={18} />
                <h3>{r.role}</h3>
                <p>{r.text}</p>
              </article>
            ))}
          </div>
        </Panel>
        <Panel
          title="Audit trail"
          subtitle="Access, exports, configuration and review actions"
          action={
            <button className="text-button" onClick={() => void refresh()}>
              Refresh
              <Icon name="refresh" size={14} />
            </button>
          }
        >
          {list("audit-events").length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Resource</th>
                    <th>Actor</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {[...list("audit-events")]
                    .sort((a, b) => b.id - a.id)
                    .slice(0, 100)
                    .map((a) => (
                      <tr key={a.id}>
                        <td>{when(a.created_at)}</td>
                        <td>
                          <strong>{label(a.action)}</strong>
                        </td>
                        <td>
                          {a.resource} {a.object_id && `#${a.object_id}`}
                        </td>
                        <td>{a.actor ? `User #${a.actor}` : "System"}</td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() =>
                              setDialog({
                                title: `Audit event #${a.id}`,
                                children: (
                                  <pre>{JSON.stringify(a.detail, null, 2)}</pre>
                                ),
                              })
                            }
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No audit events to display"
              text="Changes and protected data access are recorded here."
            />
          )}
        </Panel>
      </>
    );
  }

  if (session === undefined)
    return (
      <div className="full-loading">
        <span className="brand-symbol">W</span>
        <p>Opening your workspace…</p>
      </div>
    );
  if (!session)
    return (
      <div className="auth-page">
        <section className="auth-story">
          <div className="brand">
            <span className="brand-symbol">W</span>
            <span>
              worklens<span className="brand-dot">.</span>
            </span>
          </div>
          <div className="auth-intro">
            <span className="eyebrow">EVIDENCE INTO PERSPECTIVE</span>
            <h1>
              See the work.
              <br />
              Support the people.
            </h1>
            <p>
              A thoughtful workspace for contribution, skills and shared growth.
              Grounded in evidence. Guided by people.
            </p>
            <div className="auth-lines" aria-hidden="true">
              <span />
              <span />
              <span />
              <i />
            </div>
          </div>
          <div className="auth-values">
            <span>
              <Icon name="administration" size={17} />
              Company-controlled
            </span>
            <span>
              <Icon name="reports" size={17} />
              Explainable by design
            </span>
            <span>
              <Icon name="people" size={17} />
              Human-led decisions
            </span>
          </div>
        </section>
        <section className="auth-form-wrap">
          <div className="auth-form">
            <span className="eyebrow">
              {setup ? "YOUR FIRST STEP" : "WELCOME TO WORKLENS"}
            </span>
            <h2>
              {setup
                ? "Create your workspace."
                : "A clearer picture starts here."}
            </h2>
            <p>
              {setup
                ? "Set up the first local administrator. Organization data and source access are configured after sign-in."
                : "Sign in with your company-managed WorkLens account."}
            </p>
            <form onSubmit={authenticate}>
              <label className="field">
                <span>Username</span>
                <input
                  name="username"
                  autoComplete="username"
                  required
                  autoFocus
                />
              </label>
              {setup && (
                <label className="field">
                  <span>Administrator email</span>
                  <input
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                  />
                </label>
              )}
              <label className="field">
                <span>Password</span>
                <input
                  name="password"
                  type="password"
                  autoComplete={setup ? "new-password" : "current-password"}
                  minLength={setup ? 12 : undefined}
                  required
                />
              </label>
              {setup && (
                <small>Use a unique password of at least 12 characters.</small>
              )}
              {authError && (
                <div className="alert error" role="alert">
                  {authError}
                </div>
              )}
              <button className="button primary" disabled={authBusy}>
                {authBusy
                  ? "Please wait…"
                  : setup
                    ? "Create workspace"
                    : "Sign in"}
                <Icon name="arrow" size={17} />
              </button>
            </form>
            <div className="auth-footer">
              <Icon name="administration" size={17} />
              <p>
                Your organization controls this workspace.
                <br />
                Contact your administrator for account access.
              </p>
            </div>
          </div>
        </section>
      </div>
    );
  const title = nav.find((n) => n.page === page)?.text ?? "Workspace";
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      {mobileNav && (
        <button
          className="nav-overlay"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <button
          className="brand"
          onClick={() => navigate("overview")}
          aria-label="WorkLens overview"
        >
          <span className="brand-symbol">W</span>
          <span>
            worklens<span className="brand-dot">.</span>
          </span>
        </button>
        <div className="workspace-label">
          <span className="workspace-icon">
            <Icon name="people" size={18} />
          </span>
          <div>
            <strong>Your workspace</strong>
            <small>Company controlled</small>
          </div>
          <span className="workspace-dot" />
        </div>
        <nav aria-label="Main navigation">
          {visibleNav.map((n) => (
            <div key={n.page}>
              {n.group && <div className="nav-group">{n.group}</div>}
              <button
                aria-label={n.text}
                className={`nav-item ${page === n.page ? "active" : ""}`}
                onClick={() => navigate(n.page)}
                aria-current={page === n.page ? "page" : undefined}
              >
                <Icon name={n.page} size={19} />
                <span>{n.text}</span>
                {n.page === "reviews" && pending.length > 0 && (
                  <span className="nav-count">{pending.length}</span>
                )}
              </button>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <Icon name="administration" size={17} />
            <span>Your data. Your infrastructure.</span>
          </div>
          <div className="sidebar-user">
            <Avatar name={me?.name ?? session.username} small />
            <div>
              <strong>{me?.name ?? session.username}</strong>
              <small>{label(session.role)}</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={async () => {
                try {
                  await api("auth/logout/", "POST");
                  setSession(null);
                  setData({});
                } catch (e) {
                  notify((e as Error).message);
                }
              }}
            >
              <Icon name="logout" size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <Icon name="menu" />
            </button>
            <span>Workspace</span>
            <Icon name="chevron" size={13} />
            <strong>{title}</strong>
            {selectedEmployee && (
              <>
                <Icon name="chevron" size={13} />
                <span>{selectedEmployee.name}</span>
              </>
            )}
          </div>
          <div className="header-right">
            <span className="local-badge">
              <i />
              Self-hosted workspace
            </span>
            <button
              className="icon-button"
              aria-label="Refresh workspace"
              title="Refresh workspace"
              onClick={() => void refresh()}
            >
              <Icon name="refresh" size={18} />
            </button>
            <span className="header-separator" />
            <Avatar name={me?.name ?? session.username} small />
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <div className="page-meta">
            <span>
              <i />
              WORKLENS / {label(session.role).toUpperCase()} VIEW
            </span>
            <span>
              <Icon name="calendar" size={14} />
              {new Date().toLocaleDateString("en", {
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </div>
          {error && (
            <div className="alert error" role="alert">
              <Icon name="info" size={18} />
              <span>{error}</span>
              <button className="text-button" onClick={() => void refresh()}>
                Retry
              </button>
            </div>
          )}
          {loading && !Object.keys(data).length ? (
            <div
              className="loading-skeleton"
              role="status"
              aria-label="Loading workspace"
            >
              <div />
              <div />
              <div />
              <div />
            </div>
          ) : (
            <div className={loading ? "refreshing" : ""}>
              {employeeId
                ? profile()
                : page === "overview"
                  ? overview()
                  : page === "people"
                    ? peoplePage()
                    : page === "goals"
                      ? goalsPage()
                      : page === "skills"
                        ? skillsPage()
                        : page === "reviews"
                          ? reviewsPage()
                          : page === "sources"
                            ? sourcesPage()
                            : page === "metrics"
                              ? metricsPage()
                              : page === "reports"
                                ? reportsPage()
                                : administrationPage()}
            </div>
          )}
          <footer className="page-footer">
            <span>Evidence into perspective.</span>
            <span>Deterministic calculations · Human-led decisions</span>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Icon name="info" size={18} />
          <span>{toast}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      )}
      {dialog && (
        <DialogView
          key={dialog.title}
          dialog={dialog}
          close={closeDialog}
          done={() => {}}
        />
      )}
    </div>
  );
}
