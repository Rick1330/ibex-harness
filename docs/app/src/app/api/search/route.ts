import { search } from "@/lib/search";

export const dynamic = "force-static";
export const revalidate = false;

export const { staticGET: GET } = search;
