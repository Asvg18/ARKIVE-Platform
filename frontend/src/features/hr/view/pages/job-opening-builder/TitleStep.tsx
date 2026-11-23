import { Button } from "../../../../../shared/ui/Button";
import { ArrowRightIcon } from "../../../../../shared/ui/icons";
import { Alert } from "../../../../../shared/ui/Alert";
import { Field, StepFrame } from "./wizard";

export function TitleStep({
  title,
  error,
  onChange,
  onNext,
}: {
  title: string;
  error: string | null;
  onChange: (v: string) => void;
  onNext: () => void;
}) {
  const ready = title.trim().length > 0;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) onNext();
      }}
    >
      <StepFrame
        title="Name the role"
        sub="Use the title applicants will see on the job board."
        actions={
          <Button variant="primary" type="submit" disabled={!ready}>
            Continue
            <ArrowRightIcon width={15} height={15} aria-hidden="true" />
          </Button>
        }
      >
        <Field
          label="Job title"
          hint="The department, description, qualifications and requirements come next, drafted from the PDF or typed by you."
        >
          {(id) => (
            <input
              id={id}
              className="ark-input ark-input--lg"
              value={title}
              onChange={(e) => onChange(e.target.value)}
              placeholder="e.g. Software Engineer I"
              autoComplete="off"
              autoFocus
              aria-invalid={error ? true : undefined}
            />
          )}
        </Field>
        {error && <Alert tone="danger" title={error} />}
      </StepFrame>
    </form>
  );
}
