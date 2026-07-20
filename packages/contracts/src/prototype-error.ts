/* Generated from the processor-owned Pydantic schema. Do not edit. */

export type Code = string;
export type Debug = string | null;
export type FrameIndices = number[];
export type Message = string;
export type Retryable = boolean;
export type Stage = string;

export interface ErrorEnvelope {
  error: PrototypeError;
}
export interface PrototypeError {
  code: Code;
  debug?: Debug;
  frame_indices?: FrameIndices;
  message: Message;
  retryable?: Retryable;
  stage: Stage;
}
