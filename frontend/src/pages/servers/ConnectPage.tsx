import { useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { SERVER_NAMES, type ServerType } from "../../lib/capabilities";
import { PageHeader } from "../../components/HelpPanel";
import { Button, ButtonLink } from "../../components/Button";
import { ConnectionSteps } from "./ConnectionSteps";
import { PlexConnect } from "./PlexConnect";
import { KeyConnect } from "./KeyConnect";
import { PluginSetup } from "./PluginSetup";

export function ConnectFlow({ type, onDone }: { type: ServerType; onDone?: () => void }) {
  const [connectedAt, setConnectedAt] = useState(0);
  return (
    <div className="stack">
      {type === "plex" ? (
        <PlexConnect onConnected={() => setConnectedAt(Date.now())} />
      ) : (
        <KeyConnect type={type} onConnected={() => setConnectedAt(Date.now())} />
      )}
      {connectedAt > 0 && (
        <section className="card stack" aria-labelledby="test-title">
          <h2 id="test-title">Checking the connection</h2>
          <ConnectionSteps type={type} autoRun={connectedAt} />
          {type !== "plex" && (
            <>
              <h2>Install the Prerolls Max plugin</h2>
              <PluginSetup type={type} />
            </>
          )}
          {onDone && (
            <div>
              <Button variant="primary" onClick={onDone}>
                Continue
              </Button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export default function ConnectPage() {
  const { type } = useParams();
  const navigate = useNavigate();
  if (type !== "plex" && type !== "jellyfin" && type !== "emby") return <Navigate to="/servers" replace />;
  const name = SERVER_NAMES[type];
  return (
    <>
      <ButtonLink to="/servers" variant="ghost" size="sm" icon={<ArrowLeft size={16} aria-hidden="true" />}>
        Media Servers
      </ButtonLink>
      <PageHeader title={`Connect ${name}`} helpSlug={`connect-${type}`} />
      <ConnectFlow type={type} onDone={() => navigate("/servers")} />
    </>
  );
}
