import { useCallback, useEffect, useId, useRef, useState, type InputHTMLAttributes, type Ref } from "react";
import { EyeIcon, EyeOffIcon } from "./icons";

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  inputRef?: Ref<HTMLInputElement>;
};

/** A password field with its own show/hide control, so a person can
 * check what they typed before sending it -- every password field in
 * the app, for every role, is one of these.
 *
 * Takes everything a plain <input> does except `type`, which it owns.
 * The field hides itself again whenever its form is sent: browsers only
 * offer to save a password that is hidden at that moment, and a
 * password left on screen after signing in is one more person's to read.
 */
export function PasswordInput({ id, style, inputRef, ...rest }: PasswordInputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const [shown, setShown] = useState(false);
  const own = useRef<HTMLInputElement | null>(null);

  const setRef = useCallback(
    (el: HTMLInputElement | null) => {
      own.current = el;
      if (typeof inputRef === "function") inputRef(el);
      else if (inputRef) inputRef.current = el;
    },
    [inputRef],
  );

  useEffect(() => {
    const form = own.current?.form;
    if (!form) return;
    function hide() {
      // Directly as well as through state: the browser looks at the
      // field while the submit event is still running, before React
      // has re-rendered.
      if (own.current) own.current.type = "password";
      setShown(false);
    }
    form.addEventListener("submit", hide, true);
    return () => form.removeEventListener("submit", hide, true);
  }, []);

  const label = shown ? "Hide password" : "Show password";
  return (
    <div className="ark-reveal-wrap">
      <input
        {...rest}
        id={inputId}
        ref={setRef}
        type={shown ? "text" : "password"}
        // Shown as plain text, a phone keyboard would otherwise start
        // capitalising and "correcting" the password as it is typed.
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        style={{ ...style, paddingRight: 44 }}
      />
      <button
        type="button"
        className="ark-reveal"
        onClick={() => setShown((s) => !s)}
        // Keeps the caret in the field, so a click to check the password
        // doesn't interrupt typing it.
        onMouseDown={(e) => e.preventDefault()}
        aria-label={label}
        aria-controls={inputId}
        title={label}
      >
        {shown ? <EyeOffIcon width={17} height={17} /> : <EyeIcon width={17} height={17} />}
      </button>
    </div>
  );
}
