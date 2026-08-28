import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";
import PageNote from "../components/PageNote";

const BLANK = {
  name: "",
  keywords: "",
  mailboxes: [],
  match_subject: true,
  match_body: true,
  case_sensitive: false,
  watch_incoming: true,
  watch_outgoing: true,
  notify_telegram: true,
  max_alerts_per_hour: 20,
  is_active: true,
};

const when = (iso) => (iso ? new Date(iso).toLocaleString() : "never");

// Same IMAP presets as the Mailbox page, minus SMTP — a watch only ever reads.
const IMAP_PRESETS = [
  ["gmail.com", "imap.gmail.com"], ["googlemail.com", "imap.gmail.com"],
  ["outlook.com", "outlook.office365.com"], ["hotmail.com", "outlook.office365.com"],
  ["live.com", "outlook.office365.com"], ["office365.com", "outlook.office365.com"],
  ["yahoo.com", "imap.mail.yahoo.com"], ["ymail.com", "imap.mail.yahoo.com"],
  ["zoho.com", "imap.zoho.com"], ["icloud.com", "imap.mail.me.com"],
  ["me.com", "imap.mail.me.com"], ["titan.email", "imap.titan.email"],
];
const imapForEmail = (addr) => {
  const domain = (addr || "").split("@")[1]?.toLowerCase() || "";
  return (IMAP_PRESETS.find(([d]) => domain === d) || [])[1] || "";
};

const BLANK_MAILBOX = {
  name: "", email_address: "", username: "", password: "",
  imap_host: "", imap_port: 993, imap_use_ssl: true,
  scan_inbox: true, scan_sent: true, scan_spam: false,
  extra_folders: "", is_active: true,
};

export default function Check() {
  const [rows, setRows] = useState(null);
  const [mailboxes, setMailboxes] = useState([]);
  const [hits, setHits] = useState([]);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  const [tester, setTester] = useState(null);
  const [mbEditing, setMbEditing] = useState(null);
  const [mbBusy, setMbBusy] = useState(false);
  const toast = useToast();

  const load = () => api.watches.list().then(setRows);
  const loadHits = () => api.watchHits.list().then(setHits).catch(() => setHits([]));
  const loadMailboxes = () => api.watchMailboxes.list().then(setMailboxes);

  useEffect(() => {
    load();
    loadHits();
    loadMailboxes();
  }, []);

  const saveMailbox = async () => {
    if (!mbEditing.name.trim()) return toast("Give this mailbox a name", "err");
    if (!mbEditing.email_address.trim()) return toast("Enter the email address", "err");
    if (!mbEditing.imap_host.trim()) return toast("Enter the IMAP host", "err");
    setMbBusy(true);
    try {
      const body = { ...mbEditing };
      delete body.has_password;
      delete body.hit_count;
      delete body.last_polled_at;
      delete body.last_error;
      if (mbEditing.id) await api.watchMailboxes.update(mbEditing.id, body);
      else await api.watchMailboxes.create(body);
      setMbEditing(null);
      await loadMailboxes();
      toast("Mailbox saved");
    } catch (e) {
      toast(e.detail?.non_field_errors?.[0] || e.detail?.email_address?.[0] || "Could not save", "err");
    } finally {
      setMbBusy(false);
    }
  };

  const testMailbox = async (m) => {
    toast(`Testing ${m.name}…`);
    const res = await api.watchMailboxes.test(m.id);
    if (res.ok) toast(`Connected. Watching: ${res.folders.join(", ") || "no folders"}`);
    else toast(res.error || "Could not connect", "err");
  };

  const pollMailbox = async (m) => {
    toast(`Reading ${m.name}…`);
    try {
      const res = await api.watchMailboxes.poll(m.id);
      toast(`Read ${res.scanned} message${res.scanned === 1 ? "" : "s"}`);
      await Promise.all([loadHits(), loadMailboxes(), load()]);
    } catch (e) {
      toast(e.detail?.error || "Could not read that mailbox", "err");
    }
  };

  const removeMailbox = async (m) => {
    if (!confirm(`Stop watching "${m.name}"? Its match history goes too.`)) return;
    await api.watchMailboxes.remove(m.id);
    await Promise.all([loadMailboxes(), loadHits(), load()]);
    toast("Mailbox removed");
  };

  const onMailboxEmail = (v) => {
    const next = { ...mbEditing, email_address: v };
    if (!mbEditing.id) {
      if (!mbEditing.username || mbEditing.username === mbEditing.email_address) next.username = v;
      const host = imapForEmail(v);
      if (host && !mbEditing.imap_host) next.imap_host = host;
    }
    setMbEditing(next);
  };

  const save = async () => {
    if (!editing.name.trim()) return toast("Give this check a name", "err");
    if (!editing.keywords.trim()) return toast("Add at least one keyword", "err");
    setBusy(true);
    try {
      const body = { ...editing };
      delete body.keyword_list;
      delete body.hit_count;
      delete body.last_hit_at;
      if (editing.id) await api.watches.update(editing.id, body);
      else await api.watches.create(body);
      setEditing(null);
      await load();
      toast("Check saved");
    } catch (e) {
      toast(e.detail?.keywords?.[0] || e.detail?.non_field_errors?.[0] || "Could not save", "err");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row) => {
    if (!confirm(`Delete "${row.name}"? Its match history goes too.`)) return;
    await api.watches.remove(row.id);
    await load();
    await loadHits();
    toast("Check deleted");
  };

  const toggleActive = async (row, v) => {
    await api.watches.update(row.id, { is_active: v });
    load();
  };

  const runTest = async () => {
    const res = await api.watches.test(tester.id, { subject: tester.subject, body: tester.body });
    setTester({ ...tester, result: res });
  };

  const toggleMailbox = (id) => {
    const has = editing.mailboxes.includes(id);
    setEditing({
      ...editing,
      mailboxes: has ? editing.mailboxes.filter((m) => m !== id) : [...editing.mailboxes, id],
    });
  };

  if (!rows) return <Loader label="Loading checks…" />;

  const shown = filter ? hits.filter((h) => String(h.watch) === filter) : hits;

  return (
    <div className="grid">
      <PageNote id="check" steps={["Add the mailbox you want to keep an eye on.", "Add the words to look for, such as Promotion.", "We only read these mailboxes. We never reply from them."]}>
        Watch someone else's mailbox for words you care about.
      </PageNote>

      {/* Watched mailboxes: their own list, deliberately not the auto-reply ones. */}
      <div className="section-head">
        <span className="page-sub">
          {mailboxes.length} watched mailbox{mailboxes.length !== 1 ? "es" : ""} · read-only
        </span>
        <button className="btn btn-primary" onClick={() => setMbEditing({ ...BLANK_MAILBOX })}>
          <Icon.plus /> Add mailbox to watch
        </button>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Name</th><th>Address</th><th>IMAP</th><th>Folders</th><th>Matches</th><th>Last read</th><th>Active</th><th></th></tr>
          </thead>
          <tbody>
            {mailboxes.length === 0 && (
              <tr><td colSpan={8}><div className="empty">
                No mailboxes being watched yet. Add the campaign manager's mailbox to get started.
              </div></td></tr>
            )}
            {mailboxes.map((m) => (
              <tr key={m.id}>
                <td className="subj">{m.name}</td>
                <td className="muted">{m.email_address}</td>
                <td className="muted">{m.imap_host}</td>
                <td>
                  <div className="row" style={{ gap: 5, flexWrap: "wrap" }}>
                    {m.scan_inbox && <span className="badge badge-received">inbox</span>}
                    {m.scan_sent && <span className="badge badge-sent">sent</span>}
                    {m.scan_spam && <span className="badge badge-neutral">spam</span>}
                    {m.extra_folders && <span className="badge badge-neutral">{m.extra_folders}</span>}
                  </div>
                </td>
                <td className="mono">{m.hit_count}</td>
                <td className="mono">{when(m.last_polled_at)}</td>
                <td><Switch checked={m.is_active} onChange={async (v) => { await api.watchMailboxes.update(m.id, { is_active: v }); loadMailboxes(); }} /></td>
                <td>
                  <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                    <button className="btn btn-sm" onClick={() => testMailbox(m)}><Icon.check /> Test</button>
                    <button className="btn btn-sm" onClick={() => pollMailbox(m)}><Icon.refresh /> Read now</button>
                    <button className="btn btn-sm" onClick={() => setMbEditing({ ...m, password: "" })}><Icon.edit /></button>
                    <button className="btn btn-sm btn-danger" onClick={() => removeMailbox(m)}><Icon.trash /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {mailboxes.some((m) => m.last_error) && (
          <div className="card-pad" style={{ paddingTop: 0 }}>
            {mailboxes.filter((m) => m.last_error).map((m) => (
              <div key={m.id} className="hint-inline" style={{ color: "var(--danger)" }}>
                {m.name}: {m.last_error}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="section-head">
        <span className="page-sub">
          {rows.length} check{rows.length !== 1 ? "s" : ""} · {hits.length} recent match{hits.length !== 1 ? "es" : ""}
        </span>
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}>
          <Icon.plus /> New check
        </button>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Keywords</th><th>Mailboxes</th><th>Watching</th>
              <th>Matches</th><th>Last match</th><th>Active</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={8}><div className="empty">
                No checks yet. Add one to be told when a keyword shows up in your mail.
              </div></td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="subj">{r.name}</td>
                <td>
                  <div className="row" style={{ flexWrap: "wrap", gap: 5 }}>
                    {(r.keyword_list || []).slice(0, 4).map((k) => (
                      <span className="chip" key={k}>{k}</span>
                    ))}
                    {(r.keyword_list || []).length > 4 && (
                      <span className="muted">+{r.keyword_list.length - 4}</span>
                    )}
                  </div>
                </td>
                <td className="muted">
                  {r.mailboxes.length === 0
                    ? "All mailboxes"
                    : r.mailboxes.map((id) => mailboxes.find((m) => m.id === id)?.name || "?").join(", ")}
                </td>
                <td>
                  <div className="row" style={{ gap: 5 }}>
                    {r.watch_incoming && <span className="badge badge-received">received</span>}
                    {r.watch_outgoing && <span className="badge badge-sent">sent</span>}
                  </div>
                </td>
                <td className="mono">{r.hit_count}</td>
                <td className="mono">{when(r.last_hit_at)}</td>
                <td><Switch checked={r.is_active} onChange={(v) => toggleActive(r, v)} /></td>
                <td>
                  <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                    <button className="btn btn-sm" onClick={() => setTester({ id: r.id, name: r.name, subject: "", body: "", result: null })}>
                      <Icon.play /> Test
                    </button>
                    <button className="btn btn-sm" onClick={() => setEditing({ ...r })}><Icon.edit /></button>
                    <button className="btn btn-sm btn-danger" onClick={() => remove(r)}><Icon.trash /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* What actually matched, newest first. */}
      <div className="section-head" style={{ marginTop: 8 }}>
        <span className="page-sub">Recent matches</span>
        {rows.length > 0 && (
          <select className="input" style={{ maxWidth: 220 }} value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All checks</option>
            {rows.map((r) => <option key={r.id} value={String(r.id)}>{r.name}</option>)}
          </select>
        )}
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr><th>When</th><th>Check</th><th>Keyword</th><th>Direction</th><th>Mailbox</th><th>Subject</th><th>Alerted</th></tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={7}><div className="empty">
                Nothing has matched yet. Matches appear here as mail is checked.
              </div></td></tr>
            )}
            {shown.map((h) => (
              <tr key={h.id}>
                <td className="mono">{when(h.occurred_at || h.created_at)}</td>
                <td className="muted">{h.watch_name}</td>
                <td><span className="chip">{h.keyword}</span></td>
                <td>
                  <span className={`badge ${h.direction === "outgoing" ? "badge-sent" : "badge-received"}`}>
                    {h.direction === "outgoing" ? "sent" : "received"}
                  </span>
                </td>
                <td className="muted">{h.mailbox_name}</td>
                <td>
                  <div className="subj">{h.subject || "(no subject)"}</div>
                  <div className="muted">
                    {h.direction === "outgoing" ? `to ${h.to_addr || "—"}` : `from ${h.from_addr || "—"}`}
                    {h.excerpt ? ` · ${h.excerpt}` : ""}
                  </div>
                </td>
                <td>
                  {h.notified
                    ? <span className="badge badge-sent">sent</span>
                    : <span className="badge badge-neutral">no</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal
          title={editing.id ? "Edit check" : "New check"}
          onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          </>}
        >
          <Field label="Name">
            <input className="input" value={editing.name} placeholder="Campaign tracker"
                   onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
          </Field>

          <Field label="Keywords">
            <textarea className="textarea" style={{ minHeight: 70 }} value={editing.keywords}
                      placeholder="Promotion, Black Friday, newsletter"
                      onChange={(e) => setEditing({ ...editing, keywords: e.target.value })} />
          </Field>
          <div className="hint-inline">
            Separate with commas or new lines. A match on any one of them counts.
          </div>

          <div style={{ marginTop: 16 }}>
            <div className="page-sub" style={{ marginBottom: 6 }}>Mailboxes to watch</div>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {mailboxes.map((m) => (
                <span
                  key={m.id}
                  className="chip"
                  style={editing.mailboxes.includes(m.id)
                    ? { borderColor: "var(--brand)", color: "var(--brand)" } : undefined}
                  onClick={() => toggleMailbox(m.id)}
                >
                  {m.name}
                </span>
              ))}
            </div>
            <div className="hint-inline">
              {mailboxes.length === 0
                ? "No watched mailboxes yet — add one above first."
                : editing.mailboxes.length === 0
                  ? "None selected — every watched mailbox is included, including ones you add later."
                  : `${editing.mailboxes.length} selected.`}
            </div>
          </div>

          <div style={{ marginTop: 18 }}>
            <div className="page-sub" style={{ marginBottom: 8 }}>Where to look</div>
            <div className="row" style={{ marginBottom: 8 }}>
              <Switch checked={editing.match_subject} onChange={(v) => setEditing({ ...editing, match_subject: v })} />
              <span className="page-sub">Subject line</span>
            </div>
            <div className="row" style={{ marginBottom: 8 }}>
              <Switch checked={editing.match_body} onChange={(v) => setEditing({ ...editing, match_body: v })} />
              <span className="page-sub">Message body</span>
            </div>
            <div className="row">
              <Switch checked={editing.case_sensitive} onChange={(v) => setEditing({ ...editing, case_sensitive: v })} />
              <span className="page-sub">Match capitals exactly (off means Promotion = promotion)</span>
            </div>
          </div>

          <div style={{ marginTop: 18 }}>
            <div className="page-sub" style={{ marginBottom: 8 }}>Which mail</div>
            <div className="row" style={{ marginBottom: 8 }}>
              <Switch checked={editing.watch_incoming} onChange={(v) => setEditing({ ...editing, watch_incoming: v })} />
              <span className="page-sub">Mail that arrives — catches replies to a campaign</span>
            </div>
            <div className="row">
              <Switch checked={editing.watch_outgoing} onChange={(v) => setEditing({ ...editing, watch_outgoing: v })} />
              <span className="page-sub">Mail your team sends — catches a campaign going out</span>
            </div>
            {editing.watch_outgoing && (
              <div className="hint-inline">
                Sent mail is only read, never answered. The mailbox also needs its
                <strong> Sent</strong> folder switched on above.
              </div>
            )}
          </div>

          <div style={{ marginTop: 18 }}>
            <div className="page-sub" style={{ marginBottom: 8 }}>Telegram alerts</div>
            <div className="row" style={{ marginBottom: 10 }}>
              <Switch checked={editing.notify_telegram} onChange={(v) => setEditing({ ...editing, notify_telegram: v })} />
              <span className="page-sub">Send me a message when something matches</span>
            </div>
            {editing.notify_telegram && (
              <>
                <Field label="Most alerts per hour">
                  <input className="input" type="number" min="1" value={editing.max_alerts_per_hour}
                         onChange={(e) => setEditing({ ...editing, max_alerts_per_hour: Number(e.target.value) })} />
                </Field>
                <div className="hint-inline">
                  A busy campaign can bring hundreds of replies. After this many messages in an
                  hour we stop, then tell you the total next time. Every match still shows
                  on this page.
                </div>
              </>
            )}
          </div>

          <div className="row" style={{ marginTop: 18 }}>
            <Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} />
            <span className="page-sub">Active</span>
          </div>
        </Modal>
      )}

      {mbEditing && (
        <Modal
          title={mbEditing.id ? "Edit watched mailbox" : "Add a mailbox to watch"}
          onClose={() => setMbEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setMbEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={saveMailbox} disabled={mbBusy}>
              {mbBusy ? "Saving…" : "Save"}
            </button>
          </>}
        >
          <div className="hint-inline" style={{ marginBottom: 16 }}>
            This mailbox is only read. There is nothing to fill in for sending, and no reply can
            ever go out from it.
          </div>

          <div className="field-row">
            <Field label="Name">
              <input className="input" value={mbEditing.name} placeholder="Campaign manager"
                     onChange={(e) => setMbEditing({ ...mbEditing, name: e.target.value })} />
            </Field>
            <Field label="Email address">
              <input className="input" value={mbEditing.email_address} placeholder="manager@company.com"
                     onChange={(e) => onMailboxEmail(e.target.value)} />
            </Field>
          </div>

          <div className="field-row">
            <Field label="Username">
              <input className="input" value={mbEditing.username} placeholder="usually the email address"
                     onChange={(e) => setMbEditing({ ...mbEditing, username: e.target.value })} />
            </Field>
            <Field label={mbEditing.has_password ? "Password (leave blank to keep)" : "Password"}>
              <input className="input" type="password" value={mbEditing.password}
                     placeholder={mbEditing.has_password ? "••••••••" : "app password"}
                     onChange={(e) => setMbEditing({ ...mbEditing, password: e.target.value })} />
            </Field>
          </div>
          <div className="hint-inline">
            Most providers need an app password rather than the account's normal one.
          </div>

          <div className="field-row" style={{ marginTop: 16 }}>
            <Field label="IMAP host">
              <input className="input" value={mbEditing.imap_host} placeholder="imap.gmail.com"
                     onChange={(e) => setMbEditing({ ...mbEditing, imap_host: e.target.value })} />
            </Field>
            <Field label="IMAP port">
              <input className="input" type="number" value={mbEditing.imap_port}
                     onChange={(e) => setMbEditing({ ...mbEditing, imap_port: Number(e.target.value) })} />
            </Field>
          </div>
          <div className="row" style={{ marginBottom: 14 }}>
            <Switch checked={mbEditing.imap_use_ssl} onChange={(v) => setMbEditing({ ...mbEditing, imap_use_ssl: v })} />
            <span className="page-sub">Use SSL (port 993)</span>
          </div>

          <div className="page-sub" style={{ marginBottom: 8 }}>Which folders to read</div>
          <div className="row" style={{ marginBottom: 8 }}>
            <Switch checked={mbEditing.scan_inbox} onChange={(v) => setMbEditing({ ...mbEditing, scan_inbox: v })} />
            <span className="page-sub">Inbox — catches replies coming back</span>
          </div>
          <div className="row" style={{ marginBottom: 8 }}>
            <Switch checked={mbEditing.scan_sent} onChange={(v) => setMbEditing({ ...mbEditing, scan_sent: v })} />
            <span className="page-sub">Sent — catches campaigns going out</span>
          </div>
          <div className="row" style={{ marginBottom: 14 }}>
            <Switch checked={mbEditing.scan_spam} onChange={(v) => setMbEditing({ ...mbEditing, scan_spam: v })} />
            <span className="page-sub">Spam / Junk</span>
          </div>
          <Field label="Other folders (optional)">
            <input className="input" value={mbEditing.extra_folders} placeholder="Promotions, Archive"
                   onChange={(e) => setMbEditing({ ...mbEditing, extra_folders: e.target.value })} />
          </Field>

          <div className="row" style={{ marginTop: 14 }}>
            <Switch checked={mbEditing.is_active} onChange={(v) => setMbEditing({ ...mbEditing, is_active: v })} />
            <span className="page-sub">Active</span>
          </div>
        </Modal>
      )}

      {tester && (
        <Modal title={`Test "${tester.name}"`} onClose={() => setTester(null)}
          footer={<>
            <button className="btn" onClick={() => setTester(null)}>Close</button>
            <button className="btn btn-primary" onClick={runTest}>Check it</button>
          </>}>
          <div className="hint-inline" style={{ marginBottom: 14 }}>
            Paste a subject or some text to see if this check would spot it. Nothing is sent
            and nothing is saved.
          </div>
          <Field label="Subject">
            <input className="input" value={tester.subject}
                   onChange={(e) => setTester({ ...tester, subject: e.target.value, result: null })} />
          </Field>
          <Field label="Message body">
            <textarea className="textarea" value={tester.body}
                      onChange={(e) => setTester({ ...tester, body: e.target.value, result: null })} />
          </Field>
          {tester.result && (
            <div className="card card-pad" style={{
              padding: "10px 12px",
              borderColor: tester.result.matched ? "var(--success)" : "var(--border-strong)",
            }}>
              {tester.result.matched
                ? <span style={{ color: "var(--success)" }}>
                    ✓ Matched “{tester.result.keyword}” in the {tester.result.where}.
                  </span>
                : <span className="page-sub">No match — this one would not alert you.</span>}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
