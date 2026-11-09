import { useEffect } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { getArticle } from "../../help";
import { Markdown } from "../../components/Markdown";
import { ButtonLink } from "../../components/Button";
import { CapabilityTable } from "./CapabilityTable";

export default function HelpArticlePage() {
  const { slug = "" } = useParams();
  const article = getArticle(slug);
  const { hash } = useLocation();
  useEffect(() => {
    // Links like /help/moving-from-nexroll#help-stop-nexroll open at that section.
    const id = decodeURIComponent(hash.replace("#", ""));
    if (id) document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, [hash, slug]);
  if (!article) return <Navigate to="/help" replace />;
  return (
    <article className="help-article">
      <ButtonLink to="/help" variant="ghost" size="sm" icon={<ArrowLeft size={16} aria-hidden="true" />}>
        All help
      </ButtonLink>
      <h1>{article.title}</h1>
      <Markdown source={article.body} />
      {slug === "what-servers-can-do" && <CapabilityTable />}
    </article>
  );
}
