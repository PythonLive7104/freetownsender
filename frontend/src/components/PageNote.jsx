import { useState } from "react";
import { Icon } from "../icons";

/* A short, plain-language note at the top of a page: what this page is for and the
   first few things to do on it. Aimed at someone who has never used the app.

   Dismissal is remembered per page in localStorage, so an experienced user hides a
   note once and never sees it again. Settings → "Show page tips again" clears them
   all, so hiding is never a dead end. */

const PREFIX = "page-note-hidden:";
const keyFor = (id) => `${PREFIX}${id}`;

export function resetPageNotes() {
  try {
    Object.keys(localStorage)
      .filter((k) => k.startsWith(PREFIX))
      .forEach((k) => localStorage.removeItem(k));
  } catch {
    // Storage unavailable (private mode). Nothing was persisted, so nothing to clear.
  }
}

export default function PageNote({ id, children, steps = [] }) {
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(keyFor(id)) === "1";
    } catch {
      return false;
    }
  });

  const setBoth = (next) => {
    try {
      if (next) localStorage.setItem(keyFor(id), "1");
      else localStorage.removeItem(keyFor(id));
    } catch {
      // Storage unavailable — the note still toggles for this session.
    }
    setHidden(next);
  };

  // Collapsed, the note leaves a small toggle behind rather than vanishing, so the
  // way back is on the page itself and not buried in Settings.
  if (hidden) {
    return (
      <button className="page-note-show" onClick={() => setBoth(false)}>
        <Icon.sparkle /> Show tips
      </button>
    );
  }

  return (
    <div className="page-note">
      <div className="page-note-mark"><Icon.sparkle /></div>
      <div className="page-note-body">
        <p className="page-note-lead">{children}</p>
        {steps.length > 0 && (
          <ol className="page-note-steps">
            {steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        )}
      </div>
      <button className="btn btn-ghost btn-sm page-note-hide" onClick={() => setBoth(true)} title="Hide this note">
        Hide
      </button>
    </div>
  );
}
