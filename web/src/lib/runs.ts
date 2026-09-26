
import type {
  Basket,
  BuildRequest,
  CheaperRequest,
  CorrectionRequest,
  PickRequest,
  RefillRequest,
  SwapsRequest,
} from "./types";

export interface BuildRun {
  kind: "build";
  request: BuildRequest;
  basket: Basket;
}

export interface CorrectionRun {
  kind: "correction";
  request: CorrectionRequest;
  basket: Basket;
}

export interface RefillRun {
  kind: "refill";
  request: RefillRequest;
  basket: Basket;
}

export interface PickRun {
  kind: "pick";
  request: PickRequest;
  basket: Basket;
}

export interface CheaperRun {
  kind: "cheaper";
  request: CheaperRequest;
  basket: Basket;
}

export interface SwapsRun {
  kind: "swaps";
  request: SwapsRequest;
  basket: Basket;
}

export interface FailedRun {
  kind: "failed";
  what: RunKind;
  request:
    | BuildRequest
    | CheaperRequest
    | CorrectionRequest
    | PickRequest
    | RefillRequest
    | SwapsRequest;
  status: number | null;
  message: string;
  at: number;
}

export type DoneRun =
  BuildRun | CheaperRun | CorrectionRun | PickRun | RefillRun | SwapsRun;

export type RunKind = DoneRun["kind"];

export type Run = DoneRun | FailedRun;
