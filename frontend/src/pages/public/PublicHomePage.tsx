import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "../../components/LanguageSwitcher";
import { useAuthStore } from "../../store/authStore";
import { getPublicDemoConfig } from "../../config/publicDemo";
import "./PublicHomePage.css";

interface MetricRecord {
  value: string;
  label: string;
}

interface StageRecord {
  index: string;
  title: string;
  body: string;
}

interface ContentRecord {
  title: string;
  body: string;
}

export default function PublicHomePage() {
  const { t } = useTranslation("home");
  const token = useAuthStore((state) => state.token);
  const demoConfig = getPublicDemoConfig();
  const systemPath = token ? "/dashboard" : "/login";
  const githubUrl = "https://github.com/Open-Industry-System/OpenQMS";
  const docsUrl = `${githubUrl}/tree/main/docs`;

  const metrics = t("metrics", { returnObjects: true }) as MetricRecord[];
  const graphNodes = t("hero.graphNodes", { returnObjects: true }) as string[];
  const stages = t("ai.stages", { returnObjects: true }) as StageRecord[];
  const useCases = t("ai.useCases", { returnObjects: true }) as ContentRecord[];
  const trustLabels = t("ai.trust", { returnObjects: true }) as string[];
  const capabilities = t("capabilities.items", { returnObjects: true }) as ContentRecord[];
  const stack = t("architecture.stack", { returnObjects: true }) as string[];

  return (
    <div className="public-home">
      <header className="public-home__header">
        <nav className="public-home__nav" aria-label="OpenQMS">
          <Link className="public-home__brand" to="/">
            OpenQMS<span>.</span>
          </Link>
          <div className="public-home__nav-links">
            <a href="#ai">{t("nav.ai")}</a>
            <a href="#capabilities">{t("nav.capabilities")}</a>
            <a href="#architecture">{t("nav.architecture")}</a>
            <a href="#open-source">{t("nav.openSource")}</a>
          </div>
          <div className="public-home__nav-actions">
            <LanguageSwitcher />
            <Link className="public-home__button public-home__button--compact" to={systemPath}>
              {t("nav.enterSystem")}
            </Link>
          </div>
        </nav>
      </header>

      <main>
        <section className="public-home__hero">
          <div className="public-home__hero-grid">
            <div className="public-home__hero-copy">
              <p className="public-home__eyebrow">{t("hero.eyebrow")}</p>
              <h1>{t("hero.title")}</h1>
              <p className="public-home__lead">{t("hero.description")}</p>
              <div className="public-home__actions">
                {demoConfig && (
                  <Link className="public-home__button public-home__button--primary" to="/login?demo=viewer">
                    {t("hero.demo")}
                  </Link>
                )}
                <Link className="public-home__button" to={systemPath}>
                  {t("hero.login")}
                </Link>
                <a
                  className="public-home__text-link"
                  href={githubUrl}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {t("hero.github")} <span aria-hidden="true">↗</span>
                </a>
              </div>
            </div>

            <div className="public-home__graph" aria-hidden="true">
              <div className="public-home__graph-grid" />
              <div className="public-home__graph-orbit public-home__graph-orbit--outer" />
              <div className="public-home__graph-orbit public-home__graph-orbit--inner" />
              <div className="public-home__graph-core">
                <span>OpenQMS</span>
                <strong>{t("hero.graphLabel")}</strong>
              </div>
              {graphNodes.map((node, index) => (
                <span className={`public-home__graph-node public-home__graph-node--${index + 1}`} key={node}>
                  {node}
                </span>
              ))}
            </div>
          </div>

          <div className="public-home__metrics">
            {metrics.map((metric) => (
              <div className="public-home__metric" key={metric.label}>
                <strong>{metric.value}</strong>
                <span>{metric.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section id="ai" className="public-home__section public-home__ai">
          <div className="public-home__section-heading">
            <p className="public-home__eyebrow">{t("ai.eyebrow")}</p>
            <h2>{t("ai.title")}</h2>
            <p>{t("ai.description")}</p>
          </div>

          <div className="public-home__pipeline">
            {stages.map((stage) => (
              <article className="public-home__stage" key={stage.index}>
                <span>{stage.index}</span>
                <h3>{stage.title}</h3>
                <p>{stage.body}</p>
              </article>
            ))}
          </div>

          <div className="public-home__use-cases">
            {useCases.map((useCase) => (
              <article className="public-home__use-case" key={useCase.title}>
                <span className="public-home__node-mark" aria-hidden="true" />
                <h3>{useCase.title}</h3>
                <p>{useCase.body}</p>
              </article>
            ))}
          </div>

          <div className="public-home__trust">
            {trustLabels.map((label) => <span key={label}>{label}</span>)}
          </div>

          <aside className="public-home__principle">
            <span>{t("ai.principleLabel")}</span>
            <p>{t("ai.principle")}</p>
          </aside>
        </section>

        <section id="capabilities" className="public-home__section">
          <div className="public-home__section-heading">
            <p className="public-home__eyebrow">{t("capabilities.eyebrow")}</p>
            <h2>{t("capabilities.title")}</h2>
          </div>
          <div className="public-home__capabilities">
            {capabilities.map((capability, index) => (
              <article className="public-home__capability" key={capability.title}>
                <span>0{index + 1}</span>
                <h3>{capability.title}</h3>
                <p>{capability.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="architecture" className="public-home__section public-home__architecture">
          <div className="public-home__architecture-copy">
            <p className="public-home__eyebrow">{t("architecture.eyebrow")}</p>
            <h2>{t("architecture.title")}</h2>
            <p>{t("architecture.description")}</p>
            <div className="public-home__stack">
              {stack.map((technology) => <span key={technology}>{technology}</span>)}
            </div>
          </div>
          <div className="public-home__architecture-flow" aria-label="React through FastAPI to PostgreSQL and Neo4j">
            <div className="public-home__flow-tier">
              <span>React</span>
              <small>TypeScript</small>
            </div>
            <span className="public-home__flow-arrow" aria-hidden="true">→</span>
            <div className="public-home__flow-tier">
              <span>FastAPI</span>
              <small>SQLAlchemy</small>
            </div>
            <span className="public-home__flow-arrow" aria-hidden="true">→</span>
            <div className="public-home__flow-destinations">
              <div className="public-home__flow-tier"><span>PostgreSQL</span><small>transactions</small></div>
              <div className="public-home__flow-tier"><span>Neo4j</span><small>knowledge graph</small></div>
            </div>
          </div>
        </section>

        <section id="open-source" className="public-home__open-source">
          <p className="public-home__eyebrow">{t("openSource.eyebrow")}</p>
          <h2>{t("openSource.title")}</h2>
          <p>{t("openSource.description")}</p>
          <div className="public-home__actions public-home__actions--centered">
            <a className="public-home__button public-home__button--primary" href={githubUrl} target="_blank" rel="noreferrer noopener">
              {t("openSource.github")}
            </a>
            <a className="public-home__button" href={docsUrl} target="_blank" rel="noreferrer noopener">
              {t("openSource.docs")}
            </a>
            {demoConfig && (
              <Link className="public-home__text-link" to="/login?demo=viewer">
                {t("openSource.demo")} <span aria-hidden="true">→</span>
              </Link>
            )}
          </div>
        </section>
      </main>

      <footer className="public-home__footer">
        <span>{t("footer.license")}</span>
        <span>{t("footer.tagline")}</span>
      </footer>
    </div>
  );
}
