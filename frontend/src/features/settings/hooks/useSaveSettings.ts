import { useMutation, useQueryClient } from "@tanstack/react-query";
import { saveSettings } from "../../../shared/api/client";

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: saveSettings,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["settings-snapshot"] });
    },
  });
}
