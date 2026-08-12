/**
 * The planning engine.
 *
 * For the POC the whole methodology runs in the browser: the rules that were services
 * in the FastAPI build are the modules below, and the plan they operate on is a JSON
 * instance document fetched over HTTP. Two seams keep that reversible --
 * `instance.fetchInstance` (where the document comes from) and `workflow` (what may
 * change it). Point the first at the planning API and move the second behind it, and
 * the screens above are untouched.
 */
export * from "./constants";
export * from "./errors";
export * from "./types";

export { fteOf, isDescoped, isInPlan, rationaleOutstanding } from "./review";
export {
  DEFAULT_INSTANCE_URL,
  DEFAULT_WEIGHTS,
  cloneInstance,
  fetchInstance,
  normaliseInstance,
  prestagingDefaults,
} from "./instance";

export * as approval from "./approval";
export * as capacity from "./capacity";
export * as csv from "./csv";
export * as helios from "./helios";
export * as scheduling from "./scheduling";
export * as scoring from "./scoring";
export * as select from "./select";
export * as staging from "./staging";
export * as storage from "./storage";
export * as workflow from "./workflow";

export type { Review } from "./select";
