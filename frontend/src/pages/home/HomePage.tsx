import { useAuth } from "../../lib/auth";
import { PageHeader } from "../../components/HelpPanel";
import { ServerHealth } from "./ServerHealth";
import { IntroHealth } from "./IntroHealth";
import { NowNext } from "./NowNext";
import { SetupChecklist } from "./SetupChecklist";
import { TimeZoneWarning } from "../settings/TimeZoneSection";
import { NexrollBanner } from "../../components/NexrollBanner";

export function HomePage() {
  const { status } = useAuth();
  const name = status?.user?.display_name || status?.display_name;
  return (
    <>
      <PageHeader
        title={name ? `Hi, ${name}` : "Home"}
        description="See if everything works, and what plays before your movies."
        helpSlug="getting-started"
      />
      <NexrollBanner />
      <SetupChecklist />
      <TimeZoneWarning />
      <section className="section" aria-labelledby="working-title">
        <h2 id="working-title">Is it working?</h2>
        <div className="stack">
          <ServerHealth />
          <IntroHealth />
        </div>
      </section>
      <section className="section" aria-labelledby="now-title">
        <h2 id="now-title">What plays before movies</h2>
        <NowNext />
      </section>
    </>
  );
}
