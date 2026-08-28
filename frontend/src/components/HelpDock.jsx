import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../icons";

/* A floating map of the app, anchored bottom-right on every page.

   The problem it solves: the sidebar lists the pages grouped by category, which tells you what exists but not what to do first. New users routinely
   write a reply template, see nothing happen, and give up — because the rule that
   actually switches automation on is a separate page they never reached.

   So the panel leads with the three ordered setup steps and says plainly that the
   third is the one that turns things on. Everything else is grouped by intent
   ("watch it work", "adjust") rather than by menu position. */

const SETUP = [
  ["/mailboxes", "Mailbox", "Add the inbox you want answered", "mailbox"],
  ["/auto-reply", "Auto-reply", "Write the message to send back", "reply"],
  ["/rules", "Rules", "Join the two — this switches it on", "rules"],
];

const GROUPS = [
  ["See it working", [
    ["/listeners", "Listeners", "Live view of each inbox", "listeners"],
    ["/", "Dashboard", "Totals and recent activity", "dashboard"],
    ["/check", "Check", "Keyword alerts across your mailboxes", "watch"],
  ]],
  ["Adjust", [
    ["/configuration", "Configuration", "Check frequency, delay, signature", "config"],
    ["/placeholders", "Placeholders", "Your own reusable snippets", "placeholders"],
    ["/attachments", "Attachments", "Files to send with a reply", "attachments"],
    ["/links", "Links", "Short links that count clicks", "links"],
  ]],
  ["Account", [
    ["/team", "Team", "Share with colleagues", "team"],
    ["/security", "Security", "Password and activity log", "security"],
    ["/telegram", "Telegram", "Alerts on your phone", "telegram"],
    ["/settings", "Settings", "Your details and preferences", "settings"],
  ]],
];

export default function HelpDock({ onOpenGuide }) {
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const { pathname } = useLocation();
  const panelRef = useRef(null);

  // Close on Escape and on any click outside the panel or its button.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    const onClick = (e) => {
      if (!panelRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const go = (to) => { setOpen(false); nav(to); };

  const Row = ({ to, label, hint, icon, step }) => {
    const IconCmp = Icon[icon] || Icon.arrowRight;
    const here = pathname === to;
    return (
      <button
        className={`hd-row ${here ? "current" : ""}`}
        onClick={() => go(to)}
        aria-current={here ? "page" : undefined}
      >
        {step ? <span className="hd-step">{step}</span> : <span className="hd-icon"><IconCmp /></span>}
        <span className="hd-text">
          <span className="hd-label">{label}{here && <span className="hd-here">you are here</span>}</span>
          <span className="hd-hint">{hint}</span>
        </span>
      </button>
    );
  };

  return (
    <div className="hd" ref={panelRef}>
      {open && (
        <div className="hd-panel" role="dialog" aria-label="Where do I go?">
          <div className="hd-head">
            <div>
              <div className="hd-title">Where do I go?</div>
              <div className="hd-sub">A map of the app</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)} aria-label="Close">
              <Icon.close />
            </button>
          </div>

          <div className="hd-body">
            <div className="hd-group-label">Set up — in this order</div>
            {SETUP.map(([to, label, hint, icon], i) => (
              <Row key={to} to={to} label={label} hint={hint} icon={icon} step={i + 1} />
            ))}
            <p className="hd-aside">
              A reply is only sent once a <strong>rule</strong> connects it to an inbox.
              Writing a template on its own does nothing yet.
            </p>

            {GROUPS.map(([title, rows]) => (
              <div key={title}>
                <div className="hd-group-label">{title}</div>
                {rows.map(([to, label, hint, icon]) => (
                  <Row key={to} to={to} label={label} hint={hint} icon={icon} />
                ))}
              </div>
            ))}
          </div>

          <div className="hd-foot">
            <button className="btn btn-sm" onClick={() => { setOpen(false); onOpenGuide?.(); }}>
              <Icon.book /> Replay the full setup guide
            </button>
          </div>
        </div>
      )}

      <button
        className={`hd-toggle ${open ? "open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Close the app map" : "Open the app map — where do I go?"}
        title={open ? "Close" : "Where do I go?"}
      >
        {open ? <Icon.close /> : <Icon.help />}
        {!open && <span className="hd-toggle-text">Help</span>}
      </button>
    </div>
  );
}
