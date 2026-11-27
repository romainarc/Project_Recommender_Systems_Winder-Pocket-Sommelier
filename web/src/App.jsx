import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, Beef, Bookmark, BookmarkCheck, CakeSlice, Check, ChevronRight, Croissant,
  Drumstick, Fish, Flame, Ham, Heart, Milk, Pizza, Plus, Salad, Search, Shell, UtensilsCrossed, X,
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
const TYPE_DOT = { Red: "#6e1a2c", White: "#d9c77e", "Rosé": "#e8a09a", Sparkling: "#cdb36a", Dessert: "#c58b2c", "Dessert/Port": "#3a0e14" };
// soft stage colour per wine type: the selection reads at a glance, the page stays light
const TYPE_TINT = { Red: "#f4e6e8", White: "#f5f1df", "Rosé": "#f9e9e6", Sparkling: "#f3eddc", Dessert: "#f6ead8", "Dessert/Port": "#efe3e5" };
const tint = (type) => ({ "--tint": TYPE_TINT[type] || "#f3f1ee" });

// how many of the visitor's answers this wine matches (honest count, no made-up score)
function criteria(answers, w) {
  if (!answers) return null;
  const asked = ["color", "body", "acidity"].filter((k) => answers[k]).length
    + (answers.grapes?.length ? 1 : 0) + (answers.countries?.length ? 1 : 0);
  if (!asked) return null;
  const m = w.matched || {};
  const got = ["color", "body", "acidity", "grapes", "country"].filter((k) => m[k] && (!Array.isArray(m[k]) || m[k].length)).length;
  return { got, asked };
}

// region name in big letters behind the bottle, sized so the whole word fits the stage
function Watermark({ text, width }) {
  const word = (text || "").toUpperCase();
  if (!word) return null;
  const size = Math.max(26, Math.min(92, (width * 0.8) / (word.length * 0.64)));
  return <span className="watermark" style={{ fontSize: `${size}px` }} aria-hidden="true">{word}</span>;
}

function Criteria({ t, answers, wine }) {
  const c = criteria(answers, wine);
  if (!c) return null;
  const r = 9, len = 2 * Math.PI * r, part = c.got / c.asked;
  return (
    <span className={`criteria ${part >= 0.8 ? "high" : ""}`}>
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <circle cx="12" cy="12" r={r} fill="none" stroke="currentColor" strokeOpacity="0.18" strokeWidth="3" />
        <circle cx="12" cy="12" r={r} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"
          strokeDasharray={`${len * part} ${len}`} transform="rotate(-90 12 12)" className="criteria-arc" />
      </svg>
      {t.criteria(c.got, c.asked)}
    </span>
  );
}

const STEPS = ["color", "body", "acidity", "grapes", "countries", "discovery"];
const EMPTY_ANSWERS = { color: null, body: null, acidity: null, grapes: [], countries: [], discovery: null };
const FEATURED_GRAPES = [
  "Cabernet Sauvignon", "Merlot", "Pinot Noir", "Syrah/Shiraz", "Malbec", "Tempranillo", "Sangiovese",
  "Grenache", "Chardonnay", "Sauvignon Blanc", "Riesling", "Pinot Grigio", "Chenin Blanc", "Viognier",
  "Gamay", "Nebbiolo", "Zinfandel", "Carmenère",
];
const SESSION_KEY = "ps-session-v1";

function load(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}
function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode: the visit is kept until the page is closed */
  }
}

/* ------------------------------------------------------------------ brand */
// The mark: a fine-line wine glass that fills with wine when the page opens.
export function LogoMark({ size = 30, animate = true }) {
  const uid = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" className={`logo-mark ${animate ? "fill-anim" : ""}`}>
      <defs>
        <clipPath id={`bowl${uid}`}>
          <path d="M9.6 4.5h12.8c.6 5.6.2 10.9-6.4 11.9C9.4 15.4 9 10.1 9.6 4.5z" />
        </clipPath>
      </defs>
      <rect width="32" height="32" rx="9" fill="var(--logo-bg, #7a1f33)" />
      <g clipPath={`url(#bowl${uid})`}>
        <g className="logo-liquid">
          <path d="M2 10.5c3-1.4 5 1.4 8 0s5-1.4 8 0 5 1.4 8 0 5-1.4 8 0V20H2z" fill="#e7b9c2" />
        </g>
      </g>
      <path d="M9.6 4.5h12.8c.6 5.6.2 10.9-6.4 11.9C9.4 15.4 9 10.1 9.6 4.5z" fill="none" stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M16 16.4v7.6M11.6 26.2h8.8" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function Wordmark() {
  return (
    <span className="wordmark">
      Pocket<span className="wm-thin">Sommelier</span>
    </span>
  );
}

function CountUp({ value }) {
  const [shown, setShown] = useState(value);
  const prev = useRef(value);
  useEffect(() => {
    const from = prev.current;
    prev.current = value;
    if (from === value) return;
    let k = 0;
    const id = setInterval(() => {
      k += 1;
      setShown(Math.round(from + ((value - from) * k) / 12));
      if (k >= 12) clearInterval(id);
    }, 28);
    return () => clearInterval(id);
  }, [value]);
  return <span className="countup">{shown}</span>;
}

/* ------------------------------------------------------------------ app */
export default function App() {
  const saved = useMemo(() => load(SESSION_KEY, null), []);
  const [lang, setLang] = useState(() => load("ps-lang", "fr"));
  const t = useMemo(() => makeT(lang), [lang]);
  const [screen, setScreen] = useState(saved?.profiled ? "results" : "welcome");
  const [options, setOptions] = useState(null);
  const [error, setError] = useState(null);
  const [userId, setUserId] = useState(() => saved?.userId || newUserId());
  const [answers, setAnswers] = useState(() => saved?.answers || EMPTY_ANSWERS);
  const [profiled, setProfiled] = useState(() => saved?.profiled || false);
  const [dish, setDish] = useState(() => saved?.dish || null);
  const [wines, setWines] = useState([]);
  const [latency, setLatency] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(null);
  const [justLiked, setJustLiked] = useState(null);
  const [cellar, setCellar] = useState(() => saved?.cellar || []);
  const [liked, setLiked] = useState(() => saved?.liked || []);
  const [opinions, setOpinions] = useState(() => saved?.opinions || 0);
  const [detail, setDetail] = useState(null);
  const [composing, setComposing] = useState(false);
  const [cellarTab, setCellarTab] = useState("cellar");
  const [bump, setBump] = useState(0);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  // the visit survives a page reload; a restarted API gets the profile back in boot()
  useEffect(() => {
    save(SESSION_KEY, { userId, answers, profiled, dish, cellar, liked, opinions });
  }, [userId, answers, profiled, dish, cellar, liked, opinions]);
  useEffect(() => {
    document.documentElement.lang = lang;
    save("ps-lang", lang);
  }, [lang]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [screen]);

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

  const boot = useCallback(async () => {
    setError(null);
    try {
      setOptions(await api.options());
      if (saved?.profiled) {
        const hasAnswers = Object.values(saved.answers || {}).some((v) => (Array.isArray(v) ? v.length : v));
        if (hasAnswers) await api.onboard({ user_id: saved.userId, ...saved.answers });
        refresh(saved.dish || null, saved.userId);
      }
    } catch {
      setError("api");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    boot();
  }, [boot]);

  const showToast = (text, kind = "ok") => {
    setToast({ text, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3200);
  };

  const finishQuiz = async (final) => {
    setComposing(true);
    setAnswers(final);
    try {
      await Promise.all([api.onboard({ user_id: userId, ...final }), new Promise((r) => setTimeout(r, 1500))]);
      setProfiled(true);
      await refresh(dish);
      setScreen("results");
    } catch {
      setError("api");
    } finally {
      setComposing(false);
    }
  };

  const showPopular = () => {
    setScreen("results");
    refresh(dish);
  };

  const chooseDish = (d) => {
    setDish(d);
    refresh(d);
  };

  // like / not for me: instant feedback, then the model learns and the list is recomputed
  const opinion = async (wine, event) => {
    setBusy(wine.wine_id);
    if (event === "like") {
      setJustLiked(wine.wine_id);
      setLiked((l) => (l.some((w) => w.wine_id === wine.wine_id) ? l : [wine, ...l]));
      showToast(t.likedToast(wine.name), "like");
    } else {
      showToast(t.dislikedToast, "info");
    }
    try {
      await Promise.all([
        api.log({ user_id: userId, wine_id: wine.wine_id, event_type: event, dish }),
        new Promise((r) => setTimeout(r, event === "like" ? 800 : 250)),
      ]);
      setOpinions((n) => n + 1);
      setProfiled(true);
      setDetail(null);
      await refresh(dish);
    } catch {
      setError("api");
    } finally {
      setBusy(null);
      setJustLiked(null);
    }
  };

  // cellar: the wine stays in place; a second click takes it out
  const toggleCellar = (wine) => {
    if (cellar.some((w) => w.wine_id === wine.wine_id)) {
      setCellar((c) => c.filter((w) => w.wine_id !== wine.wine_id));
      showToast(t.removedFromCellar(wine.name), "info");
      return;
    }
    setCellar((c) => [...c, wine]);
    setBump((b) => b + 1);
    showToast(t.savedToast(wine.name), "cellar");
    api.log({ user_id: userId, wine_id: wine.wine_id, event_type: "add_to_cellar", dish }).catch(() => {});
  };

  const newVisitor = () => {
    setUserId(newUserId());
    setAnswers(EMPTY_ANSWERS);
    setProfiled(false);
    setDish(null);
    setWines([]);
    setCellar([]);
    setLiked([]);
    setOpinions(0);
    setDetail(null);
    setScreen("welcome");
  };

  if (error && !options) {
    return (
      <div className="center-page">
        <LogoMark size={56} />
        <p className="error-text">{t.errorApi}</p>
        <button className="btn btn-primary" onClick={boot}>{t.retry}</button>
      </div>
    );
  }

  const go = (s, tab) => {
    if ((s === "results" || s === "cellar") && wines.length === 0) refresh(dish);
    if (tab) setCellarTab(tab);
    setScreen(s);
  };
  const inCellar = (w) => cellar.some((c) => c.wine_id === w.wine_id);

  return (
    <div className={`app screen-${screen}`}>
      <a className="skip-link" href="#main">{lang === "fr" ? "Aller au contenu" : "Skip to content"}</a>
      <Nav
        t={t}
        screen={screen}
        cellarCount={cellar.length}
        bump={bump}
        onGo={go}
        onHome={() => setScreen("welcome")}
        onLang={() => setLang((l) => (l === "fr" ? "en" : "fr"))}
        onNewVisitor={newVisitor}
      />
      <main id="main" key={screen} className="page">
        {screen === "welcome" && <Welcome t={t} onStart={() => setScreen("quiz")} onPopular={showPopular} />}
        {screen === "quiz" && options && (
          <Quiz t={t} options={options} initial={answers} onCancel={() => setScreen(profiled ? "results" : "welcome")} onFinish={finishQuiz} />
        )}
        {screen === "results" && options && (
          <Results
            t={t}
            options={options}
            answers={answers}
            profiled={profiled}
            opinions={opinions}
            dish={dish}
            onDish={chooseDish}
            wines={wines}
            loading={loading}
            busy={busy}
            justLiked={justLiked}
            inCellar={inCellar}
            onOpinion={opinion}
            onCellar={toggleCellar}
            onOpen={setDetail}
            onQuiz={() => setScreen("quiz")}
            error={error}
            onRetry={() => refresh(dish)}
          />
        )}
        {screen === "cellar" && (
          <CellarPage
            t={t}
            tab={cellarTab}
            onTab={setCellarTab}
            cellar={cellar}
            liked={liked}
            suggestions={wines}
            answers={answers}
            busy={busy}
            inCellar={inCellar}
            onCellar={toggleCellar}
            onOpinion={opinion}
            onOpen={setDetail}
            onBack={() => go("results")}
            onQuiz={() => setScreen("quiz")}
          />
        )}
      </main>
      {(screen === "results" || screen === "cellar") && <Footer t={t} latency={latency} />}
      {detail && (
        <Detail
          t={t}
          answers={Object.values(answers).some((v) => (Array.isArray(v) ? v.length : v)) ? answers : null}
          wine={detail}
          saved={inCellar(detail)}
          busy={busy === detail.wine_id}
          onClose={() => setDetail(null)}
          onOpinion={opinion}
          onCellar={toggleCellar}
        />
      )}
      {composing && <Composing t={t} />}
      <div className={`toast ${toast ? "show" : ""}`} role="status" aria-live="polite">
        {toast && (
          <>
            <span className={`toast-icon ${toast.kind}`} aria-hidden="true">
              {toast.kind === "like" ? <Heart size={14} fill="currentColor" /> : toast.kind === "cellar" ? <BookmarkCheck size={14} /> : <Check size={14} />}
            </span>
            <span>{toast.text}</span>
          </>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ navigation, footer */
function Nav({ t, screen, cellarCount, bump, onGo, onHome, onLang, onNewVisitor }) {
  return (
    <header className="nav">
      <div className="nav-inner">
        <button className="brand" onClick={onHome} aria-label={t.brand}>
          <LogoMark size={28} />
          <Wordmark />
        </button>
        <nav className="nav-links" aria-label="Pocket Sommelier">
          <button className={`nav-link ${screen === "results" ? "active" : ""}`} onClick={() => onGo("results")}>
            {t.navSelection}
          </button>
          <button className={`nav-link ${screen === "cellar" ? "active" : ""}`} onClick={() => onGo("cellar", "cellar")}>
            {t.navCellar}
            {cellarCount > 0 && <span key={bump} className="nav-count bump">{cellarCount}</span>}
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
          <LogoMark size={26} animate={false} />
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
  const words = t.heroTitle.split(" ");
  return (
    <section className="welcome">
      <div className="welcome-copy">
        <p className="eyebrow reveal" style={{ "--d": "0ms" }}>{t.heroTitle2}</p>
        <h1 aria-label={t.heroTitle}>
          {words.map((w, i) => (
            <span key={i} className="word" style={{ "--d": `${120 + i * 70}ms` }} aria-hidden="true">{w} </span>
          ))}
        </h1>
        <p className="welcome-sub reveal" style={{ "--d": "520ms" }}>{t.heroSub}</p>
        <div className="welcome-cta reveal" style={{ "--d": "640ms" }}>
          <button className="btn btn-primary btn-lg" onClick={onStart} autoFocus>
            {t.start}
            <ArrowRight size={19} aria-hidden="true" />
          </button>
          <button className="btn-chevron" onClick={onPopular}>
            {t.skipToPopular}
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="lineup" aria-hidden="true">
        <span className="spotlight" />
        {HERO_BOTTLES.map((b, i) => (
          <div key={i} className="lineup-item" style={{ "--d": `${300 + Math.abs(2 - i) * 110}ms`, "--s": b.h / 330 }}>
            <Bottle {...b} height={b.h} />
          </div>
        ))}
      </div>
      <ol className="welcome-steps reveal" style={{ "--d": "900ms" }}>
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
  const [dir, setDir] = useState(1);
  const key = STEPS[i];
  const [title, help] = t.questions[key];
  const last = i === STEPS.length - 1;
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const go = (next) => {
    clearTimeout(timer.current);
    if (next < 0) return onCancel();
    if (next >= STEPS.length) return onFinish(a);
    setDir(next > i ? 1 : -1);
    setI(next);
  };

  const pickOne = (field, value) => {
    const v = a[field] === value ? null : value;
    setA({ ...a, [field]: v });
    clearTimeout(timer.current);
    if (v !== null && !last) timer.current = setTimeout(() => { setDir(1); setI((x) => x + 1); }, 420);
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
        <div className="pour" aria-hidden="true">
          <span className="pour-fill" style={{ "--p": (i + 1) / STEPS.length }} />
        </div>
        <p className="step-label">{t.step(i + 1, STEPS.length)}</p>
        <h1 id="quiz-title" key={`t-${key}`} className="swap">{title}</h1>
        <p className="quiz-help" key={`h-${key}`}>{help}</p>
      </div>

      <div className={`quiz-stage dir-${dir > 0 ? "next" : "prev"}`} key={key}>
        {key === "color" && (
          <div className="opts opts-6">
            {types.map((x, k) => (
              <Option key={x} k={k} style={tint(x)} selected={a.color === x} onClick={() => pickOne("color", x)} title={t.type(x)} hint={t.typeHint(x)}>
                <Bottle type={x} height={118} reflection={false} label={false} />
              </Option>
            ))}
          </div>
        )}
        {key === "body" && (
          <div className="opts opts-5">
            {bodies.map((x, k) => (
              <Option key={x} k={k} selected={a.body === x} onClick={() => pickOne("body", x)} title={t.body(x)} hint={t.bodyHint(x)}>
                <Glass level={0.22 + k * 0.18} tint={["#c9898f", "#a34a5a", "#7a1f33", "#5a1022", "#3a0712"][k]} height={110} animate />
              </Option>
            ))}
          </div>
        )}
        {key === "acidity" && (
          <div className="opts opts-3">
            {acids.map((x, k) => (
              <Option key={x} k={k} selected={a.acidity === x} onClick={() => pickOne("acidity", x)} title={t.acidity(x)} hint={t.acidityHint(x)}>
                <span className="wave"><Wave level={k + 1} height={54} /></span>
              </Option>
            ))}
          </div>
        )}
        {key === "grapes" && (
          <ChipPicker t={t} all={options.grapes} featured={grapesFeatured} selected={a.grapes} max={3} label={(x) => x} onToggle={(x) => toggleMany("grapes", x, 3)} />
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
          <button className="btn btn-quiet" onClick={() => go(i - 1)}>
            <ArrowLeft size={18} aria-hidden="true" />
            {t.back}
          </button>
          <div className="quiz-bar-right">
            {!last && <button className="btn btn-quiet" onClick={() => go(i + 1)}>{t.skip}</button>}
            <button className="btn btn-primary" onClick={() => go(i + 1)}>
              {last ? t.finish : t.next}
              <ArrowRight size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Composing({ t }) {
  return (
    <div className="composing" role="status" aria-live="polite">
      <div className="composing-glass" aria-hidden="true">
        <Glass level={0.78} tint="#7a1f33" height={180} animate slow />
      </div>
      <p className="composing-title">{t.composing}</p>
      <p className="composing-sub">{t.composingSub}</p>
      <span className="composing-line" aria-hidden="true" />
    </div>
  );
}

function Option({ k = 0, style, selected, onClick, title, hint, children }) {
  return (
    <button className={`opt ${style ? "tinted" : ""} ${selected ? "selected" : ""}`} style={{ "--d": `${k * 45}ms`, ...style }} aria-pressed={selected} onClick={onClick}>
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
        {list.map((x, k) => {
          const on = selected.includes(x);
          return (
            <button key={x} className={`chip ${on ? "on" : ""}`} style={{ "--d": `${k * 18}ms` }} aria-pressed={on} disabled={!on && selected.length >= max} onClick={() => onToggle(x)}>
              {on && <Check size={15} strokeWidth={2.6} aria-hidden="true" />}
              {label(x)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ shared bits */
function Meter({ value, max, label }) {
  return (
    <span className="meter" role="img" aria-label={label}>
      {Array.from({ length: max }, (_, k) => (
        <span key={k} className={k < value ? "on" : ""} />
      ))}
    </span>
  );
}

// a labelled scale with a marker: "Léger ——●—— Corsé"
function Scale({ value, max, left, right, label }) {
  const pct = value > 0 ? ((value - 1) / (max - 1)) * 100 : null;
  return (
    <div className="scale" role="img" aria-label={label}>
      <span className="scale-end">{left}</span>
      <span className="scale-track">
        {pct !== null && <span className="scale-dot" style={{ left: `${pct}%` }} />}
      </span>
      <span className="scale-end">{right}</span>
    </div>
  );
}

function matchPills(t, w) {
  const m = w.matched || {};
  return [
    m.color && t.type(m.color),
    m.body && t.body(m.body),
    m.acidity && `${t.acidityTitle} ${t.acidity(m.acidity).toLowerCase()}`,
    ...(m.grapes || []),
    m.country && t.country(m.country),
  ].filter(Boolean);
}

function reasonLine(t, w) {
  if (w.basis === "similar" && w.similar_to) return t.why.similar(w.similar_to);
  if (w.basis === "personal") return t.why.personal;
  if (w.basis === "popular") return t.why.popular;
  return null; // "taste": the pills say it
}

/* ------------------------------------------------------------------ results */
function TasteProfile({ t, answers, onQuiz }) {
  const bodyIdx = BODY_ORDER.indexOf(answers.body) + 1;
  const acidIdx = ACIDITY_ORDER.indexOf(answers.acidity) + 1;
  const style = answers.discovery === "safe" ? t.safeTitle : answers.discovery === "explorer" ? t.explorerTitle : null;
  const words = [...answers.grapes, ...answers.countries.map(t.country)];
  return (
    <aside className="profile-card" aria-label={t.profileCard}>
      <div className="profile-head">
        <h2>{t.profileCard}</h2>
        <button className="btn-chevron small" onClick={onQuiz}>{t.editTaste}<ChevronRight size={15} aria-hidden="true" /></button>
      </div>
      <div className="profile-row">
        <span className="profile-label">{t.pColor}</span>
        {answers.color ? (
          <span className="profile-value"><span className="type-dot" style={{ background: TYPE_DOT[answers.color] }} />{t.type(answers.color)}</span>
        ) : <span className="profile-value muted">{t.notSet}</span>}
      </div>
      <div className="profile-row">
        <span className="profile-label">{t.pBody}</span>
        <Scale value={bodyIdx} max={5} left={t.light} right={t.full} label={answers.body ? t.body(answers.body) : t.notSet} />
      </div>
      <div className="profile-row">
        <span className="profile-label">{t.pAcidity}</span>
        <Scale value={acidIdx} max={3} left={t.soft} right={t.crisp} label={answers.acidity ? t.acidity(answers.acidity) : t.notSet} />
      </div>
      <div className="profile-row">
        <span className="profile-label">{t.pStyle}</span>
        <span className={`profile-value ${style ? "" : "muted"}`}>{style || t.notSet}</span>
      </div>
      {words.length > 0 && (
        <ul className="profile-words">{words.map((w) => <li key={w}>{w}</li>)}</ul>
      )}
    </aside>
  );
}

function Results({ t, options, answers, profiled, opinions, dish, onDish, wines, loading, busy, justLiked, inCellar, onOpinion, onCellar, onOpen, onQuiz, error, onRetry }) {
  const hasAnswers = Object.values(answers).some((v) => (Array.isArray(v) ? v.length : v));
  const [hero, ...rest] = wines;
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const onScroll = () => setCompact(window.scrollY > 320);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <section className="results">
      <header className="results-head">
        <div className="results-copy">
          {profiled && <p className="greeting">{t.greeting(new Date().getHours())}</p>}
          <h1>
            {profiled ? t.yourSelection : t.popularSelection}
            {dish && <span className="h1-dish" key={dish}>{t.withDish(t.dishArticle[dish] || t.dish(dish).toLowerCase())}</span>}
          </h1>
          <p className="results-sub">{profiled ? t.selectionIntro : t.popularIntro}</p>
          {opinions > 0 && (
            <p className="learned">
              <span className="learned-dot" aria-hidden="true" />
              {t.learnedFrom(opinions).split(String(opinions))[0]}<CountUp value={opinions} />{t.learnedFrom(opinions).split(String(opinions))[1]}
            </p>
          )}
          {!profiled && <button className="btn btn-primary" onClick={onQuiz}>{t.personalize}<ArrowRight size={18} aria-hidden="true" /></button>}
        </div>
        {hasAnswers && <TasteProfile t={t} answers={answers} onQuiz={onQuiz} />}
      </header>

      <div className={`dishbar ${compact ? "compact" : ""}`} role="group" aria-label={t.eatingTonight}>
        <div className="dishbar-inner">
          <p className="dishes-label">{t.eatingTonight}</p>
          <div className="dishes-row">
            <DishButton active={!dish} onClick={() => onDish(null)} icon={UtensilsCrossed} label={t.anyDish} />
            {options.dish_families.map((f) => (
              <DishButton key={f.name} active={dish === f.name} onClick={() => onDish(f.name)} icon={DISH_ICONS[f.name] || UtensilsCrossed} label={t.dish(f.name)} />
            ))}
          </div>
        </div>
      </div>

      <div className={`results-body ${loading ? "is-loading" : ""}`} aria-busy={loading}>
        {error && (
          <div className="notice">
            <span>{t.errorApi}</span>
            <button className="btn btn-quiet" onClick={onRetry}>{t.retry}</button>
          </div>
        )}
        {wines.length === 0 && loading && <div className="hero-pick skeleton" />}
        {wines.length === 0 && !loading && <p className="empty">{t.noResult}</p>}
        {hero && (
          <HeroPick
            key={hero.wine_id}
            t={t}
            answers={hasAnswers ? answers : null}
            wine={hero}
            busy={busy === hero.wine_id}
            liked={justLiked === hero.wine_id}
            saved={inCellar(hero)}
            onOpinion={onOpinion}
            onCellar={onCellar}
            onOpen={onOpen}
          />
        )}
        {rest.length > 0 && (
          <>
            <div className="section-head">
              <h2>{t.alsoTitle}</h2>
              <p>{t.actionsHint}</p>
            </div>
            <div className="tiles">
              {rest.map((w, k) => (
                <WineTile
                  key={w.wine_id}
                  t={t}
                  answers={hasAnswers ? answers : null}
                  k={k}
                  rank={k + 2}
                  wine={w}
                  busy={busy === w.wine_id}
                  liked={justLiked === w.wine_id}
                  saved={inCellar(w)}
                  onOpinion={onOpinion}
                  onCellar={onCellar}
                  onOpen={onOpen}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function DishButton({ active, onClick, icon: Icon, label }) {
  return (
    <button className={`dish ${active ? "on" : ""}`} aria-pressed={active} onClick={onClick}>
      <span className="dish-icon"><Icon size={22} strokeWidth={1.6} aria-hidden="true" /></span>
      <span className="dish-name">{label}</span>
    </button>
  );
}

function Actions({ t, wine: w, busy, liked, saved, onOpinion, onCellar, large }) {
  return (
    <div className={`actions ${large ? "large" : ""}`}>
      <button className={`pill pill-like ${liked ? "done" : ""}`} onClick={() => onOpinion(w, "like")} disabled={busy}>
        <Heart size={17} fill={liked ? "currentColor" : "none"} aria-hidden="true" />
        {liked ? t.liked : t.likeShort}
      </button>
      <button className="pill" onClick={() => onOpinion(w, "dislike")} disabled={busy} aria-label={t.dislikeShort} title={t.dislikeShort}>
        <X size={17} aria-hidden="true" />
        {large && t.dislikeShort}
      </button>
      <button className={`pill pill-cellar ${saved ? "on" : ""}`} onClick={() => onCellar(w)} aria-pressed={saved} aria-label={saved ? t.inCellar : t.addToCellar} title={saved ? t.inCellar : t.addToCellar}>
        {saved ? <BookmarkCheck size={17} aria-hidden="true" /> : <Bookmark size={17} aria-hidden="true" />}
        {large && (saved ? t.inCellar : t.addToCellar)}
      </button>
    </div>
  );
}

function HeroPick({ t, answers, wine: w, busy, liked, saved, onOpinion, onCellar, onOpen }) {
  const pills = matchPills(t, w);
  const reason = reasonLine(t, w);
  const bodyIdx = BODY_ORDER.indexOf(w.body) + 1;
  const acidIdx = ACIDITY_ORDER.indexOf(w.acidity) + 1;
  return (
    <article className={`hero-pick ${liked ? "liked" : ""}`} aria-labelledby={`h-${w.wine_id}`}>
      <button className="hero-stage" style={tint(w.type)} onClick={() => onOpen(w)} aria-label={`${t.seeDetail} : ${w.name}`}>
        <Watermark text={w.region || w.country} width={520} />
        <span className="stage-glow" aria-hidden="true" />
        <Bottle type={w.type} grapes={w.grapes} winery={w.winery} name={w.name} height={400} />
        {liked && <span className="liked-burst" aria-hidden="true"><Heart size={56} fill="currentColor" /></span>}
      </button>
      <div className="hero-info">
        <div className="hero-top">
          <p className="eyebrow">{t.heroPickTitle}</p>
          <Criteria t={t} answers={answers} wine={w} />
        </div>
        <h2 id={`h-${w.wine_id}`}>{w.name}</h2>
        <p className="hero-place">{[w.winery, w.region, t.country(w.country)].filter(Boolean).join(" · ")}</p>
        {pills.length > 0 && (
          <ul className="match" aria-label={t.matchTitle}>
            {pills.map((p) => <li key={p}><Check size={13} strokeWidth={3} aria-hidden="true" />{p}</li>)}
          </ul>
        )}
        {reason && <p className={`reason ${w.basis}`}>{reason}</p>}
        <div className="hero-scales">
          {bodyIdx > 0 && <div><span className="profile-label">{t.pBody}</span><Scale value={bodyIdx} max={5} left={t.light} right={t.full} label={t.body(w.body)} /></div>}
          {acidIdx > 0 && <div><span className="profile-label">{t.pAcidity}</span><Scale value={acidIdx} max={3} left={t.soft} right={t.crisp} label={t.acidity(w.acidity)} /></div>}
        </div>
        {w.pairs_with && <p className="pairs">{t.why.pairs(t.dishLabel(w.pairs_with))}</p>}
        <Actions t={t} wine={w} busy={busy} liked={liked} saved={saved} onOpinion={onOpinion} onCellar={onCellar} large />
        <button className="btn-chevron" onClick={() => onOpen(w)}>{t.seeDetail}<ChevronRight size={16} aria-hidden="true" /></button>
      </div>
    </article>
  );
}

function WineTile({ t, answers, k, rank, wine: w, busy, liked, saved, onOpinion, onCellar, onOpen }) {
  // the eyebrow already says type and country: the pills only add what it does not
  const m = w.matched || {};
  const pills = [
    m.body && t.body(m.body),
    m.acidity && `${t.acidityTitle} ${t.acidity(m.acidity).toLowerCase()}`,
    ...(m.grapes || []),
  ].filter(Boolean).slice(0, 3);
  const reason = reasonLine(t, w);
  const cellarLabel = saved ? t.inCellar : t.addToCellar;
  return (
    <article className={`tile ${busy && !liked ? "leaving" : ""} ${liked ? "liked" : ""}`} style={{ "--d": `${k * 50}ms` }} aria-labelledby={`w-${w.wine_id}`}>
      <div className="tile-stage" style={tint(w.type)}>
        <button className="stage-hit" onClick={() => onOpen(w)} aria-label={`${t.seeDetail} : ${w.name}`} />
        <span className="tile-rank">{t.num(rank)}</span>
        <span className="stage-glow" aria-hidden="true" />
        <Bottle type={w.type} grapes={w.grapes} winery={w.winery} name={w.name} height={210} />
        <button className={`stage-cellar ${saved ? "on" : ""}`} onClick={() => onCellar(w)} aria-pressed={saved} aria-label={cellarLabel}>
          {saved ? <BookmarkCheck size={18} aria-hidden="true" /> : <Bookmark size={18} aria-hidden="true" />}
          <span className="stage-cellar-label">{cellarLabel}</span>
        </button>
        {liked && <span className="liked-burst" aria-hidden="true"><Heart size={42} fill="currentColor" /></span>}
      </div>
      <div className="tile-body">
        <p className="tile-eyebrow">
          {t.type(w.type)} · {t.country(w.country)}
          {(m.color || m.country) && <Check size={13} strokeWidth={3} className="eyebrow-check" aria-hidden="true" />}
        </p>
        <h3 id={`w-${w.wine_id}`} className="tile-name">
          <button className="tile-name-btn" onClick={() => onOpen(w)}>{w.name}</button>
        </h3>
        <p className="tile-place">{[w.winery, w.region].filter(Boolean).join(" · ")}</p>
        <div className="tile-meta">
          <Criteria t={t} answers={answers} wine={w} />
          {pills.length > 0 && <ul className="match">{pills.map((p) => <li key={p}><Check size={12} strokeWidth={3} aria-hidden="true" />{p}</li>)}</ul>}
          {reason && (pills.length === 0 || w.basis === "similar") && <p className={`reason ${w.basis}`}>{reason}</p>}
        </div>
      </div>
      <div className="tile-actions">
        <button className={`act act-like ${liked ? "done" : ""}`} onClick={() => onOpinion(w, "like")} disabled={busy}>
          <Heart size={16} fill={liked ? "currentColor" : "none"} aria-hidden="true" />
          {liked ? t.liked : t.likeShort}
        </button>
        <button className="act act-no" onClick={() => onOpinion(w, "dislike")} disabled={busy}>
          <X size={16} aria-hidden="true" />
          {t.dislikeShort}
        </button>
      </div>
    </article>
  );
}

/* ------------------------------------------------------------------ wine sheet (essentials only) */
function Detail({ t, answers, wine: w, saved, busy, onClose, onOpinion, onCellar }) {
  const closeRef = useRef(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);
  const pills = matchPills(t, w);
  const reason = reasonLine(t, w);
  const bodyIdx = BODY_ORDER.indexOf(w.body) + 1;
  const acidIdx = ACIDITY_ORDER.indexOf(w.acidity) + 1;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" onClick={(e) => e.stopPropagation()}>
        <button ref={closeRef} className="sheet-close" onClick={onClose} aria-label={t.close}><X size={18} aria-hidden="true" /></button>
        <div className="sheet-stage" style={tint(w.type)}>
          <Watermark text={w.region || w.country} width={370} />
          <span className="stage-glow" aria-hidden="true" />
          <Bottle type={w.type} grapes={w.grapes} winery={w.winery} name={w.name} height={400} />
        </div>
        <div className="sheet-info">
          <p className="eyebrow">{t.type(w.type)} · {t.country(w.country)}</p>
          <h2 id="sheet-title">{w.name}</h2>
          <p className="hero-place">{[w.winery, w.region].filter(Boolean).join(" · ")}</p>
          <Criteria t={t} answers={answers} wine={w} />
          {(pills.length > 0 || reason) && (
            <div className="sheet-why">
              {pills.length > 0 && <ul className="match">{pills.map((p) => <li key={p}><Check size={13} strokeWidth={3} aria-hidden="true" />{p}</li>)}</ul>}
              {reason && <p className={`reason ${w.basis}`}>{reason}</p>}
            </div>
          )}
          <div className="sheet-section">
            <h3>{t.keyFacts}</h3>
            {bodyIdx > 0 && <div className="sheet-scale"><span className="profile-label">{t.pBody}</span><Scale value={bodyIdx} max={5} left={t.light} right={t.full} label={t.body(w.body)} /></div>}
            {acidIdx > 0 && <div className="sheet-scale"><span className="profile-label">{t.pAcidity}</span><Scale value={acidIdx} max={3} left={t.soft} right={t.crisp} label={t.acidity(w.acidity)} /></div>}
            <p className="sheet-line">
              {w.grapes.slice(0, 3).join(", ")}
              {w.abv ? ` · ${w.abv.toLocaleString(t.lang)} %` : ""}
            </p>
          </div>
          {w.dishes?.length > 0 && (
            <div className="sheet-section">
              <h3>{t.pairsWithTitle}</h3>
              <p className="sheet-line">{w.dishes.slice(0, 5).map((d) => t.dishLabel(d)).join(", ")}</p>
            </div>
          )}
          <Actions t={t} wine={w} busy={busy} liked={false} saved={saved} onOpinion={onOpinion} onCellar={onCellar} large />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ cellar & favourites */
function CellarPage({ t, tab, onTab, cellar, liked, suggestions, answers, busy, inCellar, onCellar, onOpinion, onOpen, onBack, onQuiz }) {
  const list = tab === "cellar" ? cellar : liked;
  const shownIds = new Set(list.map((w) => w.wine_id));
  const ideas = suggestions.filter((w) => !shownIds.has(w.wine_id) && !inCellar(w)).slice(0, 4);
  const hasAnswers = Object.values(answers).some((v) => (Array.isArray(v) ? v.length : v));
  return (
    <section className="cellar">
      <header className="cellar-head">
        <button className="btn-back" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden="true" />
          {t.backToSelection}
        </button>
        <h1>{tab === "cellar" ? t.cellarHero : t.favorites}</h1>
        <p className="results-sub">{tab === "cellar" ? t.cellarCount(cellar.length) : t.selectionCount(liked.length)}</p>
        <div className="segmented" role="tablist">
          <button role="tab" aria-selected={tab === "cellar"} className={tab === "cellar" ? "on" : ""} onClick={() => onTab("cellar")}>
            {t.tabCellar} <span>{cellar.length}</span>
          </button>
          <button role="tab" aria-selected={tab === "favorites"} className={tab === "favorites" ? "on" : ""} onClick={() => onTab("favorites")}>
            {t.tabFavorites} <span>{liked.length}</span>
          </button>
        </div>
      </header>

      <div className="cellar-body">
        {list.length > 0 && (
          <div className="shelf">
            <ul className="shelf-row">
              {list.map((w, k) => (
                <li key={w.wine_id} className="shelf-item" style={{ "--d": `${k * 70}ms` }}>
                  <button className="shelf-bottle" onClick={() => onOpen(w)} aria-label={`${t.seeDetail} : ${w.name}`}>
                    <Bottle type={w.type} grapes={w.grapes} winery={w.winery} name={w.name} height={220} reflection={false} />
                  </button>
                </li>
              ))}
            </ul>
            <div className="shelf-line" />
            <ul className="shelf-labels">
              {list.map((w) => (
                <li key={w.wine_id} className="shelf-meta">
                  <p className="shelf-name">{w.name}</p>
                  <p className="shelf-place">{[t.type(w.type), t.country(w.country)].join(" · ")}</p>
                  {tab === "cellar" && <button className="link" onClick={() => onCellar(w)}>{t.remove}</button>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {ideas.length > 0 && (
          <div className="ideas">
            <div className="section-head">
              <h2>{list.length === 0 ? (tab === "cellar" ? t.cellarEmptyTitle : t.suggestFavTitle) : t.suggestTitle}</h2>
              {list.length === 0 && <p>{tab === "cellar" ? t.suggestTitle : t.favoritesEmpty}</p>}
            </div>
            <div className="ideas-row">
              {ideas.map((w, k) => (
                <div key={w.wine_id} className="idea" style={{ "--d": `${k * 60}ms` }}>
                  <button className="idea-stage" style={tint(w.type)} onClick={() => onOpen(w)} aria-label={`${t.seeDetail} : ${w.name}`}>
                    <Bottle type={w.type} grapes={w.grapes} winery={w.winery} name={w.name} height={170} reflection={false} />
                  </button>
                  <p className="shelf-name">{w.name}</p>
                  <p className="shelf-place">{[t.type(w.type), t.country(w.country)].join(" · ")}</p>
                  {tab === "cellar" ? (
                    <button className="pill pill-small" onClick={() => onCellar(w)}><Plus size={15} aria-hidden="true" />{t.add}</button>
                  ) : (
                    <button className="pill pill-small pill-like" onClick={() => onOpinion(w, "like")} disabled={busy === w.wine_id}><Heart size={15} aria-hidden="true" />{t.likeShort}</button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {!hasAnswers && (
          <div className="quiz-cta">
            <p>{t.profileEmpty}</p>
            <button className="btn btn-primary" onClick={onQuiz}>{t.startQuiz}</button>
          </div>
        )}
      </div>
    </section>
  );
}
