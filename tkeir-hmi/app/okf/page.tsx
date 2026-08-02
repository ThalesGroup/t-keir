import { redirect } from "next/navigation";

/** Legacy /okf route — Reporter (LLM Wiki + report) lives in the workspace sidebar. */
export default function OkfPage() {
  redirect("/?mode=reporter");
}
