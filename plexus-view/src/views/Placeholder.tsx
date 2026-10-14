import { useParams } from 'react-router-dom';

interface Props {
  title: string;
  blurb: string;
  phase?: string;
}

export function Placeholder({ title, blurb, phase = 'P3' }: Props) {
  const { id } = useParams();
  return (
    <section className="page placeholder">
      <h1>{title}</h1>
      <p>{blurb}</p>
      {id && (
        <p>
          Subject: <code>{id}</code>
        </p>
      )}
      <p className="muted">Placeholder: this view is built in {phase}.</p>
    </section>
  );
}
