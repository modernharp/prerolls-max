// What each server can do, as a table. Tap a badge for the reason.
import { FEATURE_LABELS, SERVER_NAMES, pluginWorking, useCapabilities, type Feature } from "../../lib/capabilities";
import { CapabilityBadge } from "../../components/CapabilityBadge";
import { Loading } from "../../components/Notice";

export function CapabilityTable() {
  const caps = useCapabilities();
  if (!caps.data) return <Loading />;
  const features = (Object.keys(FEATURE_LABELS) as Feature[]).filter((f) => f !== "client_notes");
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">What each media server can do with intros</caption>
        <thead>
          <tr>
            <th scope="col">What you want</th>
            {caps.data.servers.map((s) => (
              <th key={s.type} scope="col">
                {SERVER_NAMES[s.type]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {features.map((f) => (
            <tr key={f}>
              <th scope="row">{FEATURE_LABELS[f]}</th>
              {caps.data.servers.map((s) => (
                <td key={s.type}>
                  <CapabilityBadge server={s.type} info={s.features[f]} plugin={pluginWorking(s)} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
