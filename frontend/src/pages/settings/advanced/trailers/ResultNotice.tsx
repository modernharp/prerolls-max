// Several trailer endpoints answer 200 with {success, message | error, hint}
// instead of an error status. This shows any of them the same way.
import { Notice } from "../../../../components/Notice";

export interface ActionResult {
  success?: boolean;
  /** Something went wrong even though some of it worked. */
  trouble?: boolean;
  message?: string | null;
  error?: string | null;
  hint?: string | null;
}

export function resultText(result: ActionResult | undefined | null): string | null {
  if (!result) return null;
  return result.message || result.error || null;
}

export function ResultNotice({ result, title }: { result: ActionResult | undefined | null; title?: string }) {
  const text = resultText(result);
  if (!result || !text) return null;
  const tone = result.success === false ? "error" : result.trouble ? "warning" : "success";
  return (
    <Notice tone={tone} title={title}>
      <p>{text}</p>
      {result.hint && result.hint !== text && <p className="small">{result.hint}</p>}
    </Notice>
  );
}
