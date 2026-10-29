import { computed, ref, watch, type Ref } from "vue";

/** For endpoints returning a bounded snapshot. User management uses server pagination. */
export function useLocalList<T>(rows: Ref<T[]>) {
  const keyword = ref(""),
    appliedKeyword = ref(""),
    page = ref(1),
    pageSize = ref(20);
  const filtered = computed(() =>
    rows.value.filter(
      (row) =>
        !appliedKeyword.value ||
        JSON.stringify(row)
          .toLocaleLowerCase()
          .includes(appliedKeyword.value.toLocaleLowerCase()),
    ),
  );
  const total = computed(() => filtered.value.length);
  const data = computed(() =>
    filtered.value.slice(
      (page.value - 1) * pageSize.value,
      page.value * pageSize.value,
    ),
  );
  function query() {
    appliedKeyword.value = keyword.value.trim();
    page.value = 1;
  }
  function reset() {
    keyword.value = "";
    query();
  }
  watch(pageSize, () => {
    page.value = 1;
  });
  watch(total, (count) => {
    page.value = Math.min(
      page.value,
      Math.max(1, Math.ceil(count / pageSize.value)),
    );
  });
  return { keyword, page, pageSize, data, total, query, reset };
}
