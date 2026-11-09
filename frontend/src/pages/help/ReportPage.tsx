// Report a problem: builds a short report with the last error's code,
// the version and the browser, ready to copy.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Copy } from "lucide-react";
import { api } from "../../lib/api";
import { useLastError } from "../../lib/lastError";
import { formatDateTime } from "../../lib/format";
import { useServerSummary } from "../../lib/servers";
import { SERVER_NAMES } from "../../lib/capabilities";
import { PageHeader } from "../../components/HelpPanel";
import { Button, ButtonLink } from "../../components/Button";
import { TextArea } from "../../components/Field";
import { Notice } from "../../components/Notice";

export default function ReportPage() {
  const last = useLastError();
  const { connected } = useServerSummary();
  const version = useQuery({ queryKey: ["version"], queryFn: () => api.get<{ api_version: string }>("/system/version") });
  const [what, setWhat] = useState("");
  const [error, setError] = useState<string>();
  const [copied, setCopied] = useState(false);

  const report = [
    `What happened: ${what.trim() || "(not filled in)"}`,
    `Prerolls Max version: ${version.data?.api_version ?? "unknown"}`,
    `Media servers: ${connected.map((t) => SERVER_NAMES[t]).join(", ") || "none connected"}`,
    last ? `Last error: ${last.message} (code ${last.requestId ?? "none"}, ${last.path}, ${last.at})` : "Last error: none on this page",
    `Browser: ${navigator.userAgent}`,
  ].join("\n");

  const copy = async () => {
    if (!what.trim()) {
      setError("Say in a sentence or two what went wrong.");
      return;
    }
    setError(undefined);
    try {
      await navigator.clipboard.writeText(report);
      setCopied(true);
    } catch {
      setCopied(false);
      setError("Your browser didn't allow copying. Select the report below and copy it yourself.");
    }
  };

  return (
    <>
      <ButtonLink to="/help" variant="ghost" size="sm" icon={<ArrowLeft size={16} aria-hidden="true" />}>
        All help
      </ButtonLink>
      <PageHeader title="Report a problem" description="Describe what went wrong. We'll add the technical details for you." />
      <div className="card stack">
        {last ? (
          <Notice tone="info" title="The last error you saw">
            <p>
              {last.message} {formatDateTime(last.at)}.
            </p>
            {last.requestId && (
              <p>
                Error code: <code>{last.requestId}</code>. It points the developers to the exact entry in the logs.
              </p>
            )}
          </Notice>
        ) : (
          <p className="muted">No errors so far in this visit. If something went wrong earlier, describe it below.</p>
        )}
        <TextArea label="What happened?" placeholder="I clicked Save on a schedule and…" value={what} onChange={(e) => { setWhat(e.target.value); setCopied(false); }} error={error} />
        <div className="field">
          <label className="field-label" htmlFor="report-text">
            Your report
          </label>
          <pre id="report-text" className="report-preview" tabIndex={0}>
            {report}
          </pre>
        </div>
        <div className="form-actions">
          <Button variant="primary" icon={<Copy size={18} aria-hidden="true" />} onClick={copy}>
            Copy report
          </Button>
          {copied && <span role="status" className="status-ok">Copied. Paste it into your bug report.</span>}
        </div>
        <p className="muted small">
          Paste the report where you ask for help, like the project's issue tracker or forum. It contains no passwords
          or tokens.
        </p>
      </div>
    </>
  );
}
