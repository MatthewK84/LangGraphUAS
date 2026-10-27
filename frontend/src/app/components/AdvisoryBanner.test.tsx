// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { advisoryNotice } from "@/lib/advisory";
import { ADVISORY_PLAN, OPERATIONAL_PLAN, REPLAN } from "@/test/fixtures";

import { AdvisoryBanner } from "./AdvisoryBanner";

afterEach(cleanup);

describe("advisory banner (#91)", () => {
  it("renders mode, weather source and not-a-clearance", () => {
    const view = render(
      <AdvisoryBanner notice={advisoryNotice(ADVISORY_PLAN, null)} />,
    );
    expect(view.container.innerHTML).toMatchSnapshot();
  });

  it("names the replan alerts that made an operational plan advisory", () => {
    const view = render(
      <AdvisoryBanner notice={advisoryNotice(OPERATIONAL_PLAN, REPLAN)} />,
    );
    expect(view.container.innerHTML).toMatchSnapshot();
  });

  it("renders nothing when there is no notice", () => {
    const view = render(<AdvisoryBanner notice={null} />);
    expect(view.container.innerHTML).toBe("");
  });
});
