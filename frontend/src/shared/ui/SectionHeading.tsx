import { ReactNode } from "react";

type SectionHeadingProps = {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
};

export function SectionHeading({ title, description, actions }: SectionHeadingProps) {
  return (
    <div className="section-heading surface-panel__header">
      <div>
        <h2>{title}</h2>
        {description ? <p className="panel-muted">{description}</p> : null}
      </div>
      {actions ? <div className="section-heading__actions">{actions}</div> : null}
    </div>
  );
}
