import "@testing-library/jest-dom";

/**
 * openapi-fetch captures `globalThis.fetch` when `createClient` runs -- which happens as
 * `lib/api/client.ts` is imported, before any `beforeEach`. So the stub is installed here
 * at module scope; assigning it later would leave the client holding the real fetch and
 * specs would quietly hit the network.
 */
const fetchMock = jest.fn();
global.fetch = fetchMock as unknown as typeof fetch;

beforeEach(() => {
  fetchMock.mockReset();
  // An un-stubbed call fails loudly rather than reaching a real backend or hanging.
  fetchMock.mockImplementation(() =>
    Promise.reject(new Error("Unexpected network call: stub fetch in the spec")),
  );
});
