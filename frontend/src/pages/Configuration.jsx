import { useEffect, useState } from "react";
import { api } from "../api";
import { Field, Loader, Switch, useToast } from "../components/ui";
import PageNote from "../components/PageNote";

export default function Configuration() {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  useEffect(() => { api.config.get().then(setCfg); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const saved = await api.config.update(cfg);
      setCfg(saved);
      toast("Configuration saved");
    } catch { toast("Save failed", "err"); }
    finally { setBusy(false); }
  };

  if (!cfg) return <Loader />;

  return (
    <div className="grid">
      <PageNote id="configuration" steps={["Checking more often means faster replies.", "A short wait before replying feels more human.", "These settings are already fine. Change them only if you need to."]}>
        How often we check your mail, and how quickly we reply.
      </PageNote>
      <div className="card card-pad">
        <div className="between" style={{ marginBottom: 18 }}>
          <div>
            <h3>Auto-reply</h3>
            <div className="page-sub">Master switch for automatic replies</div>
          </div>
          <Switch checked={cfg.auto_reply_enabled} onChange={(v) => setCfg({ ...cfg, auto_reply_enabled: v })} />
        </div>
        <div className="field-row">
          <Field label="Reply delay (minutes)">
            <input className="input" type="number" min="0" value={cfg.reply_delay_minutes}
              onChange={(e) => setCfg({ ...cfg, reply_delay_minutes: Number(e.target.value) })} />
          </Field>
          <Field label="Poll interval (seconds)">
            <input className="input" type="number" min="5" value={cfg.poll_interval_seconds}
              onChange={(e) => setCfg({ ...cfg, poll_interval_seconds: Number(e.target.value) })} />
          </Field>
        </div>
        <Field label="Signature (appended to every auto-reply)">
          <textarea className="textarea" value={cfg.signature} onChange={(e) => setCfg({ ...cfg, signature: e.target.value })}
            placeholder="— Sent automatically by EndTime Auto-Reply" />
        </Field>

        <div className="row" style={{ marginTop: 4 }}>
          <Switch checked={cfg.reply_once_per_thread}
            onChange={(v) => setCfg({ ...cfg, reply_once_per_thread: v })} />
          <span className="page-sub">Only reply once per conversation</span>
        </div>
        <div className="hint-inline">
          {cfg.reply_once_per_thread
            ? "A person who writes again about the same subject will not get the same reply a second time. Recommended."
            : "Every matching email is answered, even if the same person already had this reply about the same subject."}
        </div>
      </div>

      <div className="card card-pad">
        <h3 style={{ marginBottom: 8 }}>How it works</h3>
        <ol className="page-sub" style={{ lineHeight: 1.9, paddingLeft: 18 }}>
          <li>Every <b>{cfg.poll_interval_seconds}s</b> the engine checks each active mailbox over IMAP.</li>
          <li>New mail is matched against your active <b>Rules</b> by subject.</li>
          <li>On a match, a reply is drafted from the template and scheduled.</li>
          {cfg.reply_once_per_thread && (
            <li>If that rule already answered this sender about this subject, it is skipped.</li>
          )}
          <li>After the <b>{cfg.reply_delay_minutes}-minute</b> delay, it's sent over SMTP.</li>
          <li>Replies are threaded back to the original sent email by subject.</li>
        </ol>
      </div>

      <div className="row">
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save configuration"}</button>
      </div>
    </div>
  );
}
