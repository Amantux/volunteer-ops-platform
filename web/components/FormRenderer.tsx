'use client';

import { useId, useMemo, useState } from 'react';
import {
  ApiError,
  submitForm,
  type FormField,
  type FormFieldCondition,
  type FormFieldOption,
  type PublicForm,
} from '@/lib/api';

interface Props {
  form: PublicForm;
}

// Each answer is a scalar (text/number/date/select), a set of values
// (multiselect), or a flag (boolean). File fields are not captured — see below.
type AnswerValue = string | boolean | string[];
type Answers = Record<string, AnswerValue>;
type Status = 'idle' | 'submitting' | 'success' | 'error';

function optionValue(o: FormFieldOption): string {
  return typeof o === 'string' ? o : o.value;
}
function optionLabel(o: FormFieldOption): string {
  return typeof o === 'string' ? o : o.label;
}

function initialValue(field: FormField): AnswerValue {
  if (field.type === 'boolean') return false;
  if (field.type === 'multiselect') return [];
  return '';
}

// Loose equality so a schema `eq: true` / `eq: 3` matches the stringy answer
// state without the caller worrying about types.
function conditionMet(cond: FormFieldCondition, answers: Answers): boolean {
  return String(answers[cond.field] ?? '') === String(cond.eq);
}

function isVisible(field: FormField, answers: Answers): boolean {
  return !field.show_if || conditionMet(field.show_if, answers);
}

function isRequired(field: FormField, answers: Answers): boolean {
  const v = field.validation;
  if (v.required) return true;
  if (v.required_if && conditionMet(v.required_if, answers)) return true;
  return false;
}

function isEmpty(value: AnswerValue): boolean {
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'boolean') return value === false;
  return value.trim() === '';
}

export default function FormRenderer({ form }: Props) {
  const baseId = useId();
  const fields = form.schema.fields;

  const [answers, setAnswers] = useState<Answers>(() => {
    const initial: Answers = {};
    for (const field of fields) initial[field.key] = initialValue(field);
    return initial;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Status>('idle');
  const [formError, setFormError] = useState('');

  // Fields shown to the submitter right now (client-side show_if evaluation).
  const visibleFields = useMemo(
    () => fields.filter((f) => isVisible(f, answers)),
    [fields, answers],
  );

  function setValue(key: string, value: AnswerValue) {
    setAnswers((prev) => ({ ...prev, [key]: value }));
  }

  function toggleMulti(key: string, option: string) {
    setAnswers((prev) => {
      const current = Array.isArray(prev[key]) ? (prev[key] as string[]) : [];
      const next = current.includes(option)
        ? current.filter((v) => v !== option)
        : [...current, option];
      return { ...prev, [key]: next };
    });
  }

  // Client-side mirror of the server rules — UX only; the server re-validates.
  function validate(): boolean {
    const next: Record<string, string> = {};
    for (const field of visibleFields) {
      if (field.type === 'file') continue;
      const value = answers[field.key];
      const required = isRequired(field, answers);

      if (required && isEmpty(value)) {
        next[field.key] =
          field.type === 'boolean'
            ? 'Please tick this box to continue.'
            : 'This field is required.';
        continue;
      }
      if (isEmpty(value)) continue;

      const v = field.validation;
      if (typeof value === 'string' && v.regex) {
        try {
          if (!new RegExp(v.regex).test(value)) {
            next[field.key] = 'Please enter a valid value.';
            continue;
          }
        } catch {
          // An unparseable server regex is not the submitter's problem — skip.
        }
      }
      if (field.type === 'number' && typeof value === 'string') {
        const n = Number(value);
        if (Number.isNaN(n)) {
          next[field.key] = 'Please enter a number.';
        } else if (v.min !== undefined && n < v.min) {
          next[field.key] = `Must be ${v.min} or more.`;
        } else if (v.max !== undefined && n > v.max) {
          next[field.key] = `Must be ${v.max} or less.`;
        }
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  // Build the answers payload from visible, non-file fields. Empty optionals are
  // omitted; numbers are coerced; booleans always send their flag.
  function buildAnswers(): Record<string, unknown> {
    const payload: Record<string, unknown> = {};
    for (const field of visibleFields) {
      if (field.type === 'file') continue;
      const value = answers[field.key];
      if (field.type === 'boolean') {
        payload[field.key] = value;
        continue;
      }
      if (isEmpty(value)) continue;
      if (field.type === 'number' && typeof value === 'string') {
        payload[field.key] = Number(value);
      } else {
        payload[field.key] = value;
      }
    }
    return payload;
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError('');
    if (!validate()) return;

    setStatus('submitting');
    try {
      await submitForm(form.key, buildAnswers());
      setStatus('success');
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError(
          'We couldn’t reach the server. Please check your connection and try again.',
        );
      }
      setStatus('error');
    }
  }

  // Success view replaces the form (the submission is logged).
  if (status === 'success') {
    return (
      <div aria-live="polite">
        <div className="alert alert-success" role="status">
          <strong>Thanks — your report has been logged</strong>
          <p>
            A reviewer will pick it up. You don’t need to do anything else.
          </p>
        </div>
      </div>
    );
  }

  function renderControl(field: FieldWithIds) {
    const { key, type } = field;
    const value = answers[key];
    const invalid = errors[key] ? 'true' : undefined;
    const describedBy = errors[key] ? field.errorId : undefined;

    switch (type) {
      case 'text':
        return (
          <textarea
            id={field.inputId}
            className="cms-textarea"
            rows={4}
            value={value as string}
            onChange={(e) => setValue(key, e.target.value)}
            aria-required={field.required || undefined}
            aria-invalid={invalid}
            aria-describedby={describedBy}
          />
        );
      case 'number':
        return (
          <input
            id={field.inputId}
            type="number"
            inputMode="decimal"
            value={value as string}
            min={field.validation.min}
            max={field.validation.max}
            onChange={(e) => setValue(key, e.target.value)}
            aria-required={field.required || undefined}
            aria-invalid={invalid}
            aria-describedby={describedBy}
          />
        );
      case 'date':
        return (
          <input
            id={field.inputId}
            type="date"
            value={value as string}
            onChange={(e) => setValue(key, e.target.value)}
            aria-required={field.required || undefined}
            aria-invalid={invalid}
            aria-describedby={describedBy}
          />
        );
      case 'select':
        return (
          <select
            id={field.inputId}
            className="cms-select"
            value={value as string}
            onChange={(e) => setValue(key, e.target.value)}
            aria-required={field.required || undefined}
            aria-invalid={invalid}
            aria-describedby={describedBy}
          >
            <option value="">Choose…</option>
            {(field.options ?? []).map((o) => (
              <option key={optionValue(o)} value={optionValue(o)}>
                {optionLabel(o)}
              </option>
            ))}
          </select>
        );
      case 'boolean':
        return (
          <label className="cms-check">
            <input
              id={field.inputId}
              type="checkbox"
              checked={value as boolean}
              onChange={(e) => setValue(key, e.target.checked)}
              aria-invalid={invalid}
              aria-describedby={describedBy}
            />
            {field.label}
          </label>
        );
      case 'file':
        return (
          <p className="hint" id={field.inputId}>
            File uploads are coming soon — please describe any attachments in the
            notes above for now.
          </p>
        );
      default:
        return null;
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      {/* Live region for form-level errors (server 422 / 429 / network). */}
      <div aria-live="assertive">
        {status === 'error' && formError && (
          <div className="alert alert-danger" role="alert">
            <strong>We couldn’t submit your report</strong>
            <p>{formError}</p>
          </div>
        )}
      </div>

      {visibleFields.map((field) => {
        const inputId = `${baseId}-${field.key}`;
        const errorId = `${inputId}-error`;
        const withIds: FieldWithIds = {
          ...field,
          inputId,
          errorId,
          required: isRequired(field, answers),
        };

        // A multiselect is a labelled group, not a single control.
        if (field.type === 'multiselect') {
          const selected = Array.isArray(answers[field.key])
            ? (answers[field.key] as string[])
            : [];
          return (
            <fieldset className="social-channels" key={field.key}>
              <legend>
                {field.label}
                {withIds.required && (
                  <span className="req" aria-hidden="true">
                    {' '}
                    *
                  </span>
                )}
              </legend>
              {(field.options ?? []).map((o) => (
                <label className="cms-check" key={optionValue(o)}>
                  <input
                    type="checkbox"
                    checked={selected.includes(optionValue(o))}
                    onChange={() => toggleMulti(field.key, optionValue(o))}
                  />
                  {optionLabel(o)}
                </label>
              ))}
              {errors[field.key] && (
                <p className="field-error" id={errorId}>
                  {errors[field.key]}
                </p>
              )}
            </fieldset>
          );
        }

        return (
          <div className="field" key={field.key}>
            {/* Boolean renders its own inline label; others label the control. */}
            {field.type !== 'boolean' && (
              <label htmlFor={inputId}>
                {field.label}
                {withIds.required && (
                  <span className="req" aria-hidden="true">
                    {' '}
                    *
                  </span>
                )}
              </label>
            )}
            {renderControl(withIds)}
            {errors[field.key] && (
              <p className="field-error" id={errorId}>
                {errors[field.key]}
              </p>
            )}
          </div>
        );
      })}

      <button
        type="submit"
        className="btn btn-primary btn-block"
        disabled={status === 'submitting'}
      >
        {status === 'submitting' ? 'Submitting…' : 'Submit report'}
      </button>
    </form>
  );
}

// A field decorated with its resolved DOM ids + required state for rendering.
interface FieldWithIds extends FormField {
  inputId: string;
  errorId: string;
  required: boolean;
}
