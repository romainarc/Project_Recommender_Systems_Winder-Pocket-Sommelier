import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, Beef, Bookmark, BookmarkCheck, CakeSlice, Check, ChevronRight, Croissant,
  Drumstick, Fish, Flame, Ham, Heart, Loader2, Milk, Pizza, Salad, Search, Shell, UtensilsCrossed, X,
} from "lucide-react";
import Bottle, { Glass, Wave } from "./Bottle.jsx";
import { api, newUserId } from "./api.js";
import { makeT, POPULAR_COUNTRIES } from "./i18n.js";

const DISH_ICONS = {
  "Red meat": Beef, Poultry: Drumstick, "Pork & charcuterie": Ham, Fish: Fish, Seafood: Shell,
  "Pasta & pizza": Pizza, Vegetarian: Salad, Cheese: Milk, "Spicy food": Flame,
  "Aperitif & snacks": Croissant, Dessert: CakeSlice,
};
const BODY_ORDER = ["Very light-bodied", "Light-bodied", "Medium-bodied", "Full-bodied", "Very full-bodied"];
const ACIDITY_ORDER = ["Low", "Medium", "High"];
const TYPE_ORDER = ["Red", "White", "Rosé", "Sparkling", "Dessert", "Dessert/Port"];
const STEPS = ["color", "body", "acidity", "grapes", "countries", "discovery"];
const EMPTY_ANSWERS = { color: null, body: null, acidity: null, grapes: [], countries: [], discovery: null };
const FEATURED_GRAPES = [
  "Cabernet Sauvignon", "Merlot", "Pinot Noir", "Syrah/Shiraz", "Malbec", "Tempranillo", "Sangiovese",
  "Grenache", "Chardonnay", "Sauvignon Blanc", "Riesling", "Pinot Grigio", "Chenin Blanc", "Viognier",
  "Gamay", "Nebbiolo", "Zinfandel", "Carmenère",
];

function readLang() {
  try {
    return localStorage.getItem("ps-lang") || "fr";
  } catch {
    return "fr";
  }
}

export function Logo({ size = 30 }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden="true" className="logo-mark">
      <rect width="40" height="40" rx="11" fill="#7a1f33" />
      <path d="M13.5 9.5h13l-.9 8.4a5.65 5.65 0 0 1-11.2 0z" fill="#fff" />
      <path d="M14.6 14.2h10.8l-.4 3.6a5.05 5.05 0 0 1-10 0z" fill="#c9566d" />
      <path d="M20 23.6v6.6M15.6 30.6h8.8" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function Wordmark() {
  return (
    <span className="wordmark">
      <span className="wm-strong">Pocket</span>
      <span className="wm-light">Sommelier</span>
    </span>
  );
}

export default function App() {
  const [lang, setLang] = useState(readLang);
  const t = useMemo(() => makeT(lang), [lang]);
  const [screen, setScreen] = useState("welcome");
  const [options, setOptions] = useState(null);
  const [error, setError] = useState(null);
  const [userId, setUserId] = useState(newUserId);
  const [answers, setAnswers] = useState(EMPTY_ANSWERS);
  const [profiled, setProfiled] = useState(false);
  const [dish, setDish] = useState(null);
  const [wines, setWines] = useState([]);
  const [latency, setLatency] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(null);
  const [cellar, setCellar] = useState([]);
  const [liked, setLiked] = useState([]);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      localStorage.setItem("ps-lang", lang);
    } catch {
      /* private mode: the choice lasts for this visit */
    }
  }, [lang]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [screen]);

  const loadOptions = useCallback(() => {
    setError(null);
    api.options().then(setOptions).catch(() => setError("api"));
  }, []);
  useEffect(loadOptions, [loadOptions]);

  const refresh = useCallback(
    async (nextDish = dish, uid = userId) => {
      setLoading(true);
      try {
        const res = await api.recommend({ user_id: uid, dish: nextDish, k: 9 });
        setWines(res.wines);
        setLatency(res.latency_ms);
        setError(null);
      } catch {
        setError("api");
      } finally {
        setLoading(false);
      }
    },
    [dish, userId],
  );

  const showToast = (text) => {
    setToast(text);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3600);
  };

  const finishQuiz = async (final) => {
    setAnswers(final);
    await api.onboard({ user_id: userId, ...final });
    setProfiled(true);
    setScreen("results");
    await refresh(dish);
  };

  const showPopular = () => {
    setScreen("results");
    refresh(dish);
  };

  const chooseDish = (d) => {
    setDish(d);
    refresh(d);
  };

  const feedback = async (wine, event) => {
    setBusy(wine.wine_id);
    try {
      await api.log({ user_id: userId, wine_id: wine.wine_id, event_type: event, dish });
      if (event === "add_to_cellar") {
        setCellar((c) => (c.some((w) => w.wine_id === wine.wine_id) ? c : [...c, wine]));
        showToast(t.savedToast(wine.name));
      } else if (event === "like") {
        setLiked((l) => (l.some((w) => w.wine_id === wine.wine_id) ? l : [wine, ...l]));
        showToast(t.likedToast(wine.name));
      } else {
        showToast(t.dislikedToast);
      }
      setProfiled(true);
      await refresh(dish);
    } catch {
      setError("api");
    } finally {
      setBusy(null);
    }
  };

  const newVisitor = () => {
    setUserId(newUserId());
    setAnswers(EMPTY_ANSWERS);
    setProfiled(false);
    setDish(null);
    setWines([]);
    setCellar([]);
    setLiked([]);
    setScreen("welcome");
  };

  if (error && !options) {
    return (
      <div className="center-page">
        <Logo size={48} />
        <p className="error-text">{t.errorApi}</p>
        <button className="btn btn-primary" onClick={loadOptions}>{t.retry}</button>
      </div>
    );
  }

  const go = (s) => {
    if (s === "results" && wines.length === 0) refresh(dish);
    setScreen(s);
  };

  return (
    <div className={`app screen-${screen}`}>
      <a className="skip-link" href="#main">{lang === "fr" ? "Aller au contenu" : "Skip to content"}</a>
      <Nav
        t={t}
        screen={screen}
        cellarCount={cellar.length}
        onGo={go}
        onHome={() => setScreen("welcome")}
        onLang={() => setLang((l) => (l === "fr" ? "en" : "fr"))}
        onNewVisitor={newVisitor}
      />
      <main id="main">
        {screen === "welcome" && <Welcome t={t} onStart={() => setScreen("quiz")} onPopular={showPopular} />}
        {screen === "quiz" && options && (
          <Quiz
            t={t}
            options={options}
            initial={answers}
            onCancel={() => setScreen(profiled ? "results" : "welcome")}
            onFinish={finishQuiz}
          />
        )}
        {screen === "results" && options && (
          <Results
            t={t}
            options={options}
            answers={answers}
            profiled={profiled}
            dish={dish}
            onDish={chooseDish}
            wines={wines}
            loading={loading}
            busy={busy}
            cellar={cellar}
            onFeedback={feedback}
            onQuiz={() => setScreen("quiz")}
            error={error}
            onRetry={() => refresh(dish)}
          />
        )}
        {screen === "cellar" && (
          <CellarPage
            t={t}
            cellar={cellar}
            liked={liked}
            answers={answers}
            profiled={profiled}
            onRemove={(id) => setCellar((c) => c.filter((w) => w.wine_id !== id))}
            onBack={() => go("results")}
            onQuiz={() => setScreen("quiz")}
          />
        )}
      </main>
      {(screen === "results" || screen === "cellar") && <Footer t={t} latency={latency} />}
      <div className={`toast ${toast ? "show" : ""}`} role="status" aria-live="polite">
        {toast && (
          <>
            <span className="toast-dot" aria-hidden="true"><Check size={14} /></span>
            <span>{toast}</span>
          </>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ navigation */
function Nav({ t, screen, cellarCount, onGo, onHome, onLang, onNewVisitor }) {
  return (
    <header className="nav">
      <div className="nav-inner">
        <button className="brand" onClick={onHome} aria-label={t.brand}>
          <Logo size={28} />
          <Wordmark />
        </button>
        <nav className="nav-links" aria-label="Pocket Sommelier">
          <button className={`nav-link ${screen === "results" ? "active" : ""}`} onClick={() => onGo("results")}>
            {t.navSelection}
          </button>
          <button className={`nav-link ${screen === "cellar" ? "active" : ""}`} onClick={() => onGo("cellar")}>
            {t.navCellar}
            {cellarCount > 0 && <span className="nav-count">{cellarCount}</span>}
          </button>
        </nav>
        <div className="nav-right">
          <button className="nav-text" onClick={onNewVisitor}>{t.newVisitor}</button>
          <button className="lang" onClick={onLang} aria-label={t.switchLang}>
            <span className={t.lang === "fr" ? "on" : ""}>FR</span>
            <span className={t.lang === "en" ? "on" : ""}>EN</span>
          </button>
        </div>
      </div>
    </header>
  );
}

function Footer({ t, latency }) {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <Logo size={22} />
          <Wordmark />
        </div>
        <p>{t.footer(Math.max(1, Math.round(latency || 1)))}</p>
        <p>{t.credits}</p>
      </div>
    </footer>
  );
}

/* ------------------------------------------------------------------ welcome */
const HERO_BOTTLES = [
  { type: "White", grapes: ["Riesling"], winery: "Domaine", name: "Riesling", h: 250 },
  { type: "Rosé", grapes: [], winery: "Côtes de Provence", name: "Rosé", h: 270 },
  { type: "Red", grapes: [], winery: "Pocket Sommelier", name: "Grand Vin", h: 330 },
  { type: "Sparkling", grapes: [], winery: "Maison", name: "Brut", h: 300 },
  { type: "White", grapes: ["Chardonnay"], winery: "Bourgogne", name: "Chardonnay", h: 262 },
];

function Welcome({ t, onStart, onPopular }) {
  return (
    <section className="welcome">
      <div className="welcome-copy">
        <p className="eyebrow">{t.heroTitle2}</p>
        <h1>{t.heroTitle}</h1>
        <p className="welcome-sub">{t.heroSub}</p>
        <div className="welcome-cta">
          <button className="btn btn-primary btn-lg" onClick={onStart} autoFocus>
            {t.start}
          </button>
          <button className="btn-chevron" onClick={onPopular}>
            {t.skipToPopular}
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="lineup" aria-hidden="true">
        {HERO_BOTTLES.map((b, i) => (
          <div key={i} className="lineup-item" style={{ animationDelay: `${i * 70}ms`, "--s": b.h / 330 }}>
            <Bottle {...b} height={b.h} />
          </div>
        ))}
      </div>
      <ol className="welcome-steps">
        {t.stepsShort.map((s, i) => (
          <li key={s}>
            <span className="ws-num">{i + 1}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/* ------------------------------------------------------------------ questionnaire */
function Quiz({ t, options, initial, onCancel, onFinish }) {
  const [i, setI] = useState(0);
  const [a, setA] = useState(initial);
  const [sending, setSending] = useState(false);
  const key = STEPS[i];
  const [title, help] = t.questions[key];
  const last = i === STEPS.length - 1;
  const timer = useRef(null);

  const go = async (next) => {
    clearTimeout(timer.current);
    if (next < 0) return onCancel();
    if (next >= STEPS.length) {
      setSending(true);
      await onFinish(a);
      return;
    }
    setI(next);
  };

  const pickOne = (field, value) => {
    const v = a[field] === value ? null : value;
    setA({ ...a, [field]: v });
    clearTimeout(timer.current);
    if (v !== null && !last) timer.current = setTimeout(() => setI((x) => x + 1), 380);
  };

  const toggleMany = (field, value, max) => {
    const list = a[field];
    if (list.includes(value)) setA({ ...a, [field]: list.filter((x) => x !== value) });
    else if (list.length < max) setA({ ...a, [field]: [...list, value] });
  };

  const types = TYPE_ORDER.filter((x) => options.color.includes(x));
  const bodies = BODY_ORDER.filter((x) => options.body.includes(x));
  const acids = ACIDITY_ORDER.filter((x) => options.acidity.includes(x));
  const grapesFeatured = FEATURED_GRAPES.filter((g) => options.grapes.includes(g));

  return (
    <section className="quiz" aria-labelledby="quiz-title">
      <div className="quiz-head">
        <div className="steps-bar" aria-hidden="true">
          {STEPS.map((s, k) => (
            <span key={s} className={k < i ? "done" : k === i ? "now" : ""} />
          ))}
        </div>
        <p className="step-label">{t.step(i + 1, STEPS.length)}</p>
        <h1 id="quiz-title">{title}</h1>
        <p className="quiz-help">{help}</p>
      </div>

      <div className="quiz-stage" key={key}>
        {key === "color" && (
          <div className="opts opts-6">
            {types.map((x) => (
              <Option key={x} selected={a.color === x} onClick={() => pickOne("color", x)} title={t.type(x)} hint={t.typeHint(x)}>
                <Bottle type={x} height={118} reflection={false} label={false} />
              </Option>
            ))}
          </div>
        )}
        {key === "body" && (
          <div className="opts opts-5">
            {bodies.map((x, k) => (
              <Option key={x} selected={a.body === x} onClick={() => pickOne("body", x)} title={t.body(x)} hint={t.bodyHint(x)}>
                <Glass level={0.22 + k * 0.18} tint={["#c9898f", "#a34a5a", "#7a1f33", "#5a1022", "#3a0712"][k]} height={110} />
              </Option>
            ))}
          </div>
        )}
        {key === "acidity" && (
          <div className="opts opts-3">
            {acids.map((x, k) => (
              <Option key={x} selected={a.acidity === x} onClick={() => pickOne("acidity", x)} title={t.acidity(x)} hint={t.acidityHint(x)}>
                <span className="wave"><Wave level={k + 1} height={54} /></span>
              </Option>
            ))}
          </div>
        )}
        {key === "grapes" && (
          <ChipPicker
            t={t}
            all={options.grapes}
            featured={grapesFeatured}
            selected={a.grapes}
            max={3}
            label={(x) => x}
            onToggle={(x) => toggleMany("grapes", x, 3)}
          />
        )}
        {key === "countries" && (
          <ChipPicker
            t={t}
            all={options.countries}
            featured={POPULAR_COUNTRIES.filter((c) => options.countries.includes(c))}
            selected={a.countries}
            max={2}
            label={t.country}
            onToggle={(x) => toggleMany("countries", x, 2)}
          />
        )}
        {key === "discovery" && (
          <div className="opts opts-2">
            <StyleCard
              selected={a.discovery === "safe"}
              onClick={() => pickOne("discovery", "safe")}
              title={t.safeTitle}
              text={t.safeText}
              bottles={[
                { type: "Red", winery: "Château", name: "Grand Vin" },
                { type: "Sparkling", winery: "Maison", name: "Brut" },
                { type: "White", grapes: ["Chardonnay"], winery: "Domaine", name: "Premier Cru" },
              ]}
            />
            <StyleCard
              selected={a.discovery === "explorer"}
              onClick={() => pickOne("discovery", "explorer")}
              title={t.explorerTitle}
              text={t.explorerText}
              explorer
              bottles={[
                { type: "White", grapes: ["Riesling"], winery: "Kakheti", name: "Qvevri" },
                { type: "Dessert", winery: "Tokaj", name: "Aszú" },
                { type: "Rosé", winery: "Santorini", name: "Assyrtiko" },
              ]}
            />
          </div>
        )}
      </div>

      <div className="quiz-bar">
        <div className="quiz-bar-inner">
          <button className="btn btn-quiet" onClick={() => go(i - 1)} disabled={sending}>
            <ArrowLeft size={18} aria-hidden="true" />
            {t.back}
          </button>
          <div className="quiz-bar-right">
            {!last && (
              <button className="btn btn-quiet" onClick={() => go(i + 1)}>{t.skip}</button>
            )}
            <button className="btn btn-primary" onClick={() => go(i + 1)} disabled={sending}>
              {sending ? (
                <>
                  <Loader2 className="spin" size={18} aria-hidden="true" />
                  {t.preparing}
                </>
              ) : (
                <>
                  {last ? t.finish : t.next}
                  <ArrowRight size={18} aria-hidden="true" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Option({ selected, onClick, title, hint, children }) {
  return (
    <button className={`opt ${selected ? "selected" : ""}`} aria-pressed={selected} onClick={onClick}>
      <span className="opt-art">{children}</span>
      <span className="opt-title">{title}</span>
      <span className="opt-hint">{hint}</span>
      <span className="opt-check" aria-hidden="true"><Check size={14} strokeWidth={3} /></span>
    </button>
  );
}

function StyleCard({ selected, onClick, title, text, bottles, explorer }) {
  return (
    <button className={`style-card ${explorer ? "explorer" : "safe"} ${selected ? "selected" : ""}`} aria-pressed={selected} onClick={onClick}>
      <span className="style-art" aria-hidden="true">
        {bottles.map((b, k) => (
          <span key={k} className={`style-bottle b${k}`}>
            <Bottle {...b} height={k === 1 ? 190 : 165} reflection={false} />
          </span>
        ))}
      </span>
      <span className="style-copy">
        <span className="style-title">{title}</span>
        <span className="style-text">{text}</span>
      </span>
      <span className="opt-check" aria-hidden="true"><Check size={14} strokeWidth={3} /></span>
    </button>
  );
}

function ChipPicker({ t, all, featured, selected, max, label, onToggle }) {
  const [q, setQ] = useState("");
  const shown = q
    ? all.filter((x) => label(x).toLowerCase().includes(q.toLowerCase()) || x.toLowerCase().includes(q.toLowerCase()))
    : featured;
  const list = [...selected.filter((x) => !shown.includes(x)), ...shown].slice(0, 24);
  return (
    <div className="picker">
      <div className="picker-top">
        <label className="search">
          <Search size={18} aria-hidden="true" />
          <input type="search" value={q} placeholder={t.search} onChange={(e) => setQ(e.target.value)} aria-label={t.search} />
        </label>
        <span className="picker-count">{t.upTo(max)} · {selected.length}/{max}</span>
      </div>
      <div className="chips">
        {list.map((x) => {
          const on = selected.includes(x);
          return (
            <button key={x} className={`chip ${on ? "on" : ""}`} aria-pressed={on} disabled={!on && selected.length >= max} onClick={() => onToggle(x)}>
              {on && <Check size={15} strokeWidth={2.6} aria-hidden="true" />}
              {label(x)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Meter({ value, max, label }) {
  return (
    <span className="meter" role="img" aria-label={label}>
      {Array.from({ length: max }, (_, k) => (
        <span key={k} className={k < value ? "on" : ""} />
      ))}
    </span>
  );
}

/* ------------------------------------------------------------------ results */
function tasteSummary(t, answers) {
  return [
    answers.color && t.type(answers.color),
    answers.body && t.body(answers.body),
    answers.acidity && `${t.acidityTitle} ${t.acidity(answers.acidity).toLowerCase()}`,
    ...answers.grapes,
    ...answers.countries.map(t.country),
    answers.discovery && (answers.discovery === "safe" ? t.safeTitle : t.explorerTitle),
  ].filter(Boolean);
}

function Results({ t, options, answers, profiled, dish, onDish, wines, loading, busy, cellar, onFeedback, onQuiz, error, onRetry }) {
  const summary = tasteSummary(t, answers);
  return (
    <section className="results">
      <header className="results-head">
        <h1>{profiled ? t.yourSelection : t.popularSelection}</h1>
        <p className="results-sub">{profiled ? t.selectionIntro : t.popularIntro}</p>
        {profiled && summary.length > 0 ? (
          <div className="taste-line">
            <ul className="taste-pills" aria-label={t.tasteSummary}>
              {summary.map((s) => <li key={s}>{s}</li>)}
            </ul>
            <button className="btn-chevron" onClick={onQuiz}>{t.editTaste}<ChevronRight size={16} aria-hidden="true" /></button>
          </div>
        ) : (
          !profiled && <button className="btn btn-primary" onClick={onQuiz}>{t.personalize}</button>
        )}
      </header>

      <div className="dishes" role="group" aria-label={t.eatingTonight}>
        <p className="dishes-label">{t.eatingTonight}</p>
        <div className="dishes-row">
          <DishButton active={!dish} onClick={() => onDish(null)} icon={UtensilsCrossed} label={t.anyDish} />
          {options.dish_families.map((f) => (
            <DishButton key={f.name} active={dish === f.name} onClick={() => onDish(f.name)} icon={DISH_ICONS[f.name] || UtensilsCrossed} label={t.dish(f.name)} />
          ))}
        </div>
      </div>

      {error && (
        <div className="notice">
          <span>{t.errorApi}</span>
          <button className="btn btn-quiet" onClick={onRetry}>{t.retry}</button>
        </div>
      )}

      <p className="hint-line">{t.actionsHint}</p>

      <div className={`tiles ${loading ? "is-loading" : ""}`} aria-busy={loading}>
        {wines.length === 0 && loading && Array.from({ length: 6 }, (_, k) => <div key={k} className="tile skeleton" />)}
        {wines.length === 0 && !loading && <p className="empty">{t.noResult}</p>}
        {wines.map((w, k) => (
          <WineTile key={w.wine_id} t={t} rank={k + 1} wine={w} busy={busy === w.wine_id} saved={cellar.some((c) => c.wine_id === w.wine_id)} onFeedback={onFeedback} />
        ))}
      </div>
    </section>
  );
}

function DishButton({ active, onClick, icon: Icon, label }) {
  return (
    <button className={`dish ${active ? "on" : ""}`} aria-pressed={active} onClick={onClick}>
      <span className="dish-icon"><Icon size={24} strokeWidth={1.6} aria-hidden="true" /></span>
      <span className="dish-name">{label}</span>
    </button>
  );
}

function reasonText(t, w) {
  if (w.basis === "similar" && w.similar_to) return t.why.similar(w.similar_to);
  if (w.basis === "taste") {
    const m = w.matched || {};
    const parts = [
      m.color && t.type(m.color).toLowerCase(),
      m.body && t.body(m.body).toLowerCase(),
      m.acidity && `${t.acidityTitle.toLowerCase()} ${t.acidity(m.acidity).toLowerCase()}`,
      ...(m.grapes || []),
      m.country && t.country(m.country),
    ].filter(Boolean);
    return `${t.why.taste}${t.lang === "fr" ? " : " : ": "}${parts.join(", ")}`;
  }
  if (w.basis === "personal") return t.why.personal;
  return t.why.popular;
}

function WineTile({ t, rank, wine: w, busy, saved, onFeedback }) {
  const bodyLevel = BODY_ORDER.indexOf(w.body) + 1;
  const acidLevel = ACIDITY_ORDER.indexOf(w.acidity) + 1;
  const place = [w.region, t.country(w.country)].filter(Boolean).join(", ");
  const safe = w.popularity_rank <= 500;
  return (
    <article className={`tile ${busy ? "leaving" : ""}`} aria-labelledby={`w-${w.wine_id}`}>
      <div className="tile-stage">
        <span className="tile-rank" aria-label={t.rankLabel(rank)}>{String(rank).padStart(2, "0")}</span>
        <span className={`tile-badge ${safe ? "safe" : "disc"}`}>{safe ? t.safeBadge : t.discoveryBadge}</span>
        <Bottle type={w.type} grapes={w.grapes} winery={w.winery} name={w.name} height={236} />
      </div>
      <div className="tile-body">
        <p className="tile-eyebrow">{t.type(w.type)}</p>
        <h2 id={`w-${w.wine_id}`} className="tile-name">{w.name}</h2>
        <p className="tile-place" title={[w.winery, place].filter(Boolean).join(" · ")}>
          {[w.winery, place].filter(Boolean).join(" · ")}
        </p>
        <dl className="tile-facts">
          {bodyLevel > 0 && (
            <div><dt>{t.bodyTitle}</dt><dd><Meter value={bodyLevel} max={5} label={t.body(w.body)} /></dd></div>
          )}
          {acidLevel > 0 && (
            <div><dt>{t.acidityTitle}</dt><dd><Meter value={acidLevel} max={3} label={t.acidity(w.acidity)} /></dd></div>
          )}
          {w.abv ? (
            <div><dt>{t.abv}</dt><dd>{w.abv.toLocaleString(t.lang)} %</dd></div>
          ) : null}
        </dl>
        {w.grapes.length > 0 && <p className="tile-grapes">{w.grapes.slice(0, 3).join(", ")}</p>}
        <div className={`tile-why ${w.basis}`}>
          <p>{reasonText(t, w)}</p>
          {w.pairs_with && <p className="tile-pairs">{t.why.pairs(t.dishLabel(w.pairs_with))}</p>}
        </div>
      </div>
      <div className="tile-actions">
        <div className="tile-actions-row">
          <button className="pill pill-like" onClick={() => onFeedback(w, "like")} disabled={busy}>
            <Heart size={17} aria-hidden="true" />
            {t.likeShort}
          </button>
          <button className="pill" onClick={() => onFeedback(w, "dislike")} disabled={busy}>
            <X size={17} aria-hidden="true" />
            {t.dislikeShort}
          </button>
        </div>
        <button className={`cellar-btn ${saved ? "on" : ""}`} onClick={() => onFeedback(w, "add_to_cellar")} disabled={busy || saved}>
          {saved ? <BookmarkCheck size={17} aria-hidden="true" /> : <Bookmark size={17} aria-hidden="true" />}
          {saved ? t.inCellar : t.addToCellar}
        </button>
      </div>
    </article>
  );
}

/* ------------------------------------------------------------------ cellar page */
function CellarPage({ t, cellar, liked, answers, profiled, onRemove, onBack, onQuiz }) {
  const summary = tasteSummary(t, answers);
  const hasAnswers = summary.length > 0;
  const byType = TYPE_ORDER.map((ty) => [ty, cellar.filter((w) => w.type === ty).length]).filter(([, n]) => n);
  return (
    <section className="cellar">
      <header className="cellar-head">
        <button className="btn-back" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden="true" />
          {t.backToSelection}
        </button>
        <h1>{t.cellarHero}</h1>
        <p className="cellar-count">
          {t.cellarCount(cellar.length)}
          {byType.length > 0 && <span> · {byType.map(([ty, n]) => `${n} ${t.type(ty).toLowerCase()}${n > 1 && !t.type(ty).endsWith("s") ? "s" : ""}`).join(", ")}</span>}
        </p>
      </header>

      {cellar.length === 0 ? (
        <div className="shelf-empty">
          <div className="ghosts" aria-hidden="true">
            {["Red", "White", "Sparkling", "Rosé", "Red"].map((ty, k) => (
              <span key={k} className="ghost"><Bottle type={ty} height={180} reflection={false} label={false} /></span>
            ))}
          </div>
          <div className="shelf-line" />
          <h2>{t.cellarEmptyTitle}</h2>
          <p>{t.cellarEmptyText}</p>
          <button className="btn btn-primary" onClick={onBack}>{t.backToSelection}</button>
        </div>
      ) : (
        <div className="shelf">
          <ul className="shelf-row" aria-hidden="true">
            {cellar.map((w) => (
              <li key={w.wine_id} className="shelf-item">
                <Bottle type={w.type} grapes={w.grapes} winery={w.winery} name={w.name} height={220} reflection={false} />
              </li>
            ))}
          </ul>
          <div className="shelf-line" />
          <ul className="shelf-labels">
            {cellar.map((w) => (
              <li key={w.wine_id} className="shelf-meta">
                <p className="shelf-name">{w.name}</p>
                <p className="shelf-place">{[t.type(w.type), t.country(w.country)].join(" · ")}</p>
                <button className="link" onClick={() => onRemove(w.wine_id)}>{t.remove}</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="cellar-panels">
        <div className="panel">
          <h2>{t.favorites}</h2>
          {liked.length === 0 ? (
            <p className="panel-empty">{t.favoritesEmpty}</p>
          ) : (
            <ul className="fav-list">
              {liked.map((w) => (
                <li key={w.wine_id}>
                  <span className="fav-art"><Bottle type={w.type} grapes={w.grapes} height={70} reflection={false} label={false} /></span>
                  <div>
                    <p className="fav-name">{w.name}</p>
                    <p className="fav-meta">{[w.winery, t.country(w.country)].filter(Boolean).join(" · ")}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel">
          <h2>{t.profileTitle}</h2>
          {hasAnswers ? (
            <>
              <ul className="taste-pills">{summary.map((s) => <li key={s}>{s}</li>)}</ul>
              <button className="btn-chevron" onClick={onQuiz}>{t.editTaste}<ChevronRight size={16} aria-hidden="true" /></button>
            </>
          ) : (
            <>
              <p className="panel-empty">{profiled ? t.noAnswers : t.profileEmpty}</p>
              <button className="btn btn-primary" onClick={onQuiz}>{t.startQuiz}</button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
