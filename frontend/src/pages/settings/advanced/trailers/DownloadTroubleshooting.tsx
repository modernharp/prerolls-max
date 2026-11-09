// "If downloads fail": YouTube now asks some servers to prove they aren't
// robots. Cookies from a signed-in browser, or the YouTube helper (it makes
// the "PO token" proof YouTube asks for), get past it.
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { api } from "../../../../lib/api";
import { Button } from "../../../../components/Button";
import { ErrorNotice, Loading } from "../../../../components/Notice";
import { ResultNotice, type ActionResult } from "./ResultNotice";

interface Diagnostics {
  yt_dlp_available?: boolean;
  yt_dlp_version?: string;
  ffmpeg_available?: boolean;
  cookies_file_exists?: boolean;
}

interface PoToken extends ActionResult {
  usable?: boolean;
  installed?: boolean;
  running?: boolean;
  node_available?: boolean;
  provider_present?: boolean;
}

interface Dependency {
  available?: boolean;
  installable?: boolean;
}

function Check({ ok, yes, no }: { ok: boolean | undefined; yes: React.ReactNode; no: React.ReactNode }) {
  return (
    <li className="check-step">
      {ok ? <CheckCircle2 size={20} className="status-ok" aria-hidden="true" /> : <XCircle size={20} className="status-bad" aria-hidden="true" />}
      <span>{ok ? yes : no}</span>
    </li>
  );
}

export function DownloadTroubleshooting() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const diag = useQuery({ queryKey: ["trailer-diag"], queryFn: () => api.get<Diagnostics>("/nexup/download/diagnostics", undefined, { timeoutMs: 30_000 }) });
  const token = useQuery({ queryKey: ["potoken"], queryFn: () => api.get<PoToken>("/nexup/potoken/status"), retry: false });
  const deps = useQuery({
    queryKey: ["dependencies"],
    queryFn: async () => (await api.get<{ dependencies: Record<string, Dependency> }>("/system/dependencies", undefined, { timeoutMs: 30_000 })).dependencies,
    retry: false,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["trailer-diag"] });
    void queryClient.invalidateQueries({ queryKey: ["potoken"] });
    void queryClient.invalidateQueries({ queryKey: ["dependencies"] });
  };
  const cookies = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.post<ActionResult>("/nexup/youtube/upload-cookies", form);
    },
    onSuccess: refresh,
  });
  const startToken = useMutation({ mutationFn: () => api.post<PoToken>("/nexup/potoken/start", {}, { timeoutMs: 120_000 }), onSuccess: refresh });
  const installToken = useMutation({
    mutationFn: () => api.post<ActionResult>("/system/dependencies/install/potoken", {}, { timeoutMs: 15 * 60_000 }),
    onSuccess: refresh,
  });
  const testDownload = useMutation({
    mutationFn: () => api.post<ActionResult>("/nexup/youtube/test-download", {}, { timeoutMs: 180_000 }),
  });
  const helperRunning = Boolean(token.data?.usable);
  // Outside Docker the helper may not be installed yet; the page can do it.
  const canInstall = Boolean(token.data && !token.data.provider_present && deps.data?.potoken?.installable);
  const startAnswer: ActionResult | undefined = startToken.data
    ? startToken.data.usable
      ? { success: true, message: "The helper is running. Press Try a test download to check." }
      : { success: false, message: startToken.data.message || startToken.data.hint || "The helper didn't start." }
    : undefined;

  return (
    <div className="stack">
      <p>
        YouTube sometimes stops servers from downloading until they show they aren't a robot. When that happens, trailers
        stop arriving. Two things help:
      </p>
      {diag.isLoading ? (
        <Loading />
      ) : diag.isError ? (
        <ErrorNotice error={diag.error} />
      ) : (
        <ul className="check-steps">
          <Check
            ok={diag.data?.yt_dlp_available}
            yes={`The downloader is installed${diag.data?.yt_dlp_version ? ` (${diag.data.yt_dlp_version})` : ""}`}
            no="The downloader (yt-dlp) isn't installed"
          />
          <Check ok={diag.data?.ffmpeg_available} yes="FFmpeg is installed" no="FFmpeg isn't installed" />
          <Check ok={diag.data?.cookies_file_exists} yes="YouTube cookies are saved" no="No YouTube cookies saved" />
          <Check ok={helperRunning} yes="The YouTube helper is running" no="The YouTube helper isn't running" />
        </ul>
      )}
      <h4>1. Cookies from your browser</h4>
      <p className="muted small">
        Sign in to YouTube in your browser, export its cookies as a cookies.txt file with a browser extension, then upload
        the file here. Prerolls Max keeps it private and only sends it to YouTube.
      </p>
      <div>
        <Button size="sm" loading={cookies.isPending} onClick={() => fileRef.current?.click()}>
          Upload cookies.txt
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,text/plain"
          className="visually-hidden"
          aria-label="cookies.txt file"
          tabIndex={-1}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) cookies.mutate(file);
            e.target.value = "";
          }}
        />
      </div>
      <ResultNotice result={cookies.data} />
      {cookies.isError && <ErrorNotice error={cookies.error} />}
      <h4>2. The YouTube helper</h4>
      <p className="muted small">
        A small helper makes the proof YouTube asks for (a &ldquo;PO token&rdquo;). It needs Node.js on this computer. The
        Docker image comes with both. Starting it can take a minute the first time.
      </p>
      <div className="form-actions">
        {canInstall ? (
          <Button size="sm" loading={installToken.isPending} onClick={() => installToken.mutate()}>
            Install the helper
          </Button>
        ) : (
          <Button size="sm" loading={startToken.isPending} disabled={helperRunning} onClick={() => startToken.mutate()}>
            {helperRunning ? "Helper is running" : "Start the helper"}
          </Button>
        )}
        <Button size="sm" loading={testDownload.isPending} onClick={() => testDownload.mutate()}>
          Try a test download
        </Button>
      </div>
      {installToken.isPending && <p className="muted small">Downloading and setting up the helper. This can take a few minutes.</p>}
      <ResultNotice result={installToken.data} />
      <ResultNotice result={startAnswer} />
      {(startToken.isError || installToken.isError) && <ErrorNotice error={startToken.error ?? installToken.error} />}
      <ResultNotice result={testDownload.data} />
      {testDownload.isError && <ErrorNotice error={testDownload.error} />}
    </div>
  );
}
