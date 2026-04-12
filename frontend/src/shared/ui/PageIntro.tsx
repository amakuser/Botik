import { ReactNode } from "react";

type PageIntroProps = {
  title: string;
  description: string;
  eyebrow?: string;
  meta?: ReactNode;
};

export function PageIntro({ title, description, eyebrow, meta }: PageIntroProps) {
  return (
    <section className="page-intro panel">
      <div className="page-intro__body">
        {eyebrow ? <p className="page-intro__eyebrow">{eyebrow}</p> : null}
        <h2 className="page-intro__title">{title}</h2>
        <p className="page-intro__description">{description}</p>
      </div>
      {meta ? <div className="page-intro__meta">{meta}</div> : null}
    </section>
  );
}
