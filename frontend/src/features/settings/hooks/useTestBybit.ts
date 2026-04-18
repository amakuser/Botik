import { useMutation } from "@tanstack/react-query";
import { testBybitApi } from "../../../shared/api/client";

export function useTestBybit() {
  return useMutation({ mutationFn: testBybitApi });
}
