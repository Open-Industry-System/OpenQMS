import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "../../components/LanguageSwitcher";
import { getPublicDemoConfig } from "../../config/publicDemo";
import { useAuthStore } from "../../store/authStore";
import "./PublicHomePage.css";

interface TranslatedMetric {
  value: string;
  label: string;
}

interface TranslatedStage {
  index: string;
  title: string;
  body: string;
}

interface TranslatedContent {
  title: string;
  body: string;
}

export default function PublicHomePage() {
  const { t } = useTranslation("home");
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const demoConfig = getPublicDemoConfig();
  const systemPath = token && user ? "/dashboard" : "/login";
  const githubUrl = "https://github.com/Open-Industry-System/OpenQMS";
  const docsUrl = `${githubUrl}/tree/main/docs`;

  const metrics = t("metrics", { returnObjects: true }) as TranslatedMetric[];
  const graphNodes = t("hero.graphNodes", { returnObjects: true }) as string[];
  const stages = t("ai.stages", { returnObjects: true }) as TranslatedStage[];
  const useCases = t("ai.useCases", { returnObjects: true }) as TranslatedContent[];
  const trustLabels = t("ai.trust", { returnObjects: true }) as string[];
  const capabilities = t("capabilities.items", { returnObjects: true }) as TranslatedContent[];
  const stack = t("architecture.stack", { returnObjects: true }) as string[];
  const demoPath = demoConfig ? "/login?demo=viewer" : null;

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
            <Link className="public-home__nav-entry" to={systemPath}>
              {t("nav.enterSystem")}
            </Link>
          </div>
        </nav>
      </header>

      <main>
        <section className="public-home__hero">
          <div className="public-home__hero-inner">
            <div className="public-home__hero-copy">
              <p className="public-home__eyebrow">{t("hero.eyebrow")}</p>
              <h1>{t("hero.title")}</h1>
              <p className="public-home__lead">{t("hero.description")}</p>

              <div className="public-home__actions">
                {demoPath && (
                  <Link className="public-home__button public-home__button--primary" to={demoPath}>
                    {t("hero.demo")}
                  </Link>
                )}
                <Link className="public-home__button public-home__button--secondary" to={systemPath}>
                  {t("hero.login")}
                </Link>
                <a
                  className="public-home__text-link"
                  href={githubUrl}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {t("hero.github")}
                </a>
              </div>
            </div>

            <div className="public-home__graph" aria-hidden="true">
              <div className="public-home__graph-orbit public-home__graph-orbit--outer" />
              <div className="public-home__graph-orbit public-home__graph-orbit--inner" />
              <div className="public-home__graph-core">{t("hero.graphLabel")}</div>
              {graphNodes.map((node, index) => (
                <div
                  className={`public-home__graph-node public-home__graph-node--${index + 1}`}
                  key={node}
                >
                  {node}
                </div>
              ))}
            </div>

            <div className="public-home__metrics">
              {metrics.map((metric) => (
                <div className="public-home__metric" key={metric.label}>
                  <strong>{metric.value}</strong>
                  <span>{metric.label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="ai" className="public-home__section public-home__ai">
          <div className="public-home__section-heading">
            <p className="public-home__eyebrow">{t("ai.eyebrow")}</p>
            <h2>{t("ai.title")}</h2>
            <p>{t("ai.description")}</p>
          </div>

          <div className="public-home__stages">
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
              <article className="public-home__card public-home__use-case" key={useCase.title}>
                <h3>{useCase.title}</h3>
                <p>{useCase.body}</p>
              </article>
            ))}
          </div>

          <div className="public-home__trust">
            {trustLabels.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>

          <aside className="public-home__principle">
            <strong>{t("ai.principleLabel")}</strong>
            <p>{t("ai.principle")}</p>
          </aside>
        </section>

        <section id="capabilities" className="public-home__section">
          <div className="public-home__section-heading">
            <p className="public-home__eyebrow">{t("capabilities.eyebrow")}</p>
            <h2>{t("capabilities.title")}</h2>
          </div>

          <div className="public-home__capabilities">
            {capabilities.map((capability) => (
              <article className="public-home__card public-home__capability" key={capability.title}>
                <h3>{capability.title}</h3>
                <p>{capability.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section
          id="architecture"
          className="public-home__section public-home__architecture"
        >
          <div className="public-home__architecture-copy">
            <p className="public-home__eyebrow">{t("architecture.eyebrow")}</p>
            <h2>{t("architecture.title")}</h2>
            <p>{t("architecture.description")}</p>
          </div>

          <div className="public-home__architecture-flow">
            <div className="public-home__architecture-tier public-home__architecture-tier--frontend">
              <span>{stack[0]}</span>
            </div>
            <div className="public-home__architecture-tier public-home__architecture-tier--api">
              <span>{stack[1]}</span>
              <span>{stack[2]}</span>
            </div>
            <div className="public-home__architecture-tier public-home__architecture-tier--data">
              <span>{stack[3]}</span>
              <span>{stack[4]}</span>
              <span>{stack[5]}</span>
            </div>
            <div className="public-home__architecture-tier public-home__architecture-tier--runtime">
              <span>{stack[6]}</span>
            </div>
          </div>
        </section>

        <section id="open-source" className="public-home__open-source">
          <p className="public-home__eyebrow">{t("openSource.eyebrow")}</p>
          <h2>{t("openSource.title")}</h2>
          <p>{t("openSource.description")}</p>
          <div className="public-home__actions public-home__actions--centered">
            <a
              className="public-home__button public-home__button--primary"
              href={githubUrl}
              target="_blank"
              rel="noreferrer noopener"
            >
              {t("openSource.github")}
            </a>
            <a
              className="public-home__button public-home__button--secondary"
              href={docsUrl}
              target="_blank"
              rel="noreferrer noopener"
            >
              {t("openSource.docs")}
            </a>
            {demoPath && (
              <Link className="public-home__text-link" to={demoPath}>
                {t("openSource.demo")}
              </Link>
            )}
          </div>
        </section>
      </main>

      <footer className="public-home__footer">
        <span>{t("footer.license")}</span>
        <div className="public-home__footer-links">
          <a
            href={githubUrl}
            target="_blank"
            rel="noreferrer noopener"
          >
            {t("openSource.github")}
          </a>
          <a
            href={docsUrl}
            target="_blank"
            rel="noreferrer noopener"
          >
            {t("openSource.docs")}
          </a>
        </div>
        <span>{t("footer.tagline")}</span>
      </footer>
    </div>
  );
}
