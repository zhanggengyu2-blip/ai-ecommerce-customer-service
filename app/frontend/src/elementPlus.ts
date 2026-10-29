import type { App, Component } from "vue";

import { ElAlert } from "element-plus/es/components/alert/index.mjs";
import "element-plus/es/components/alert/style/css";
import { ElBreadcrumb } from "element-plus/es/components/breadcrumb/index.mjs";
import "element-plus/es/components/breadcrumb/style/css";
import { ElBreadcrumbItem } from "element-plus/es/components/breadcrumb/index.mjs";
import "element-plus/es/components/breadcrumb-item/style/css";
import { ElButton } from "element-plus/es/components/button/index.mjs";
import "element-plus/es/components/button/style/css";
import { ElCard } from "element-plus/es/components/card/index.mjs";
import "element-plus/es/components/card/style/css";
import { ElCheckbox } from "element-plus/es/components/checkbox/index.mjs";
import "element-plus/es/components/checkbox/style/css";
import { ElCollapse } from "element-plus/es/components/collapse/index.mjs";
import "element-plus/es/components/collapse/style/css";
import { ElCollapseItem } from "element-plus/es/components/collapse/index.mjs";
import "element-plus/es/components/collapse-item/style/css";
import { ElDatePicker } from "element-plus/es/components/date-picker/index.mjs";
import "element-plus/es/components/date-picker/style/css";
import { ElDescriptions } from "element-plus/es/components/descriptions/index.mjs";
import "element-plus/es/components/descriptions/style/css";
import { ElDescriptionsItem } from "element-plus/es/components/descriptions/index.mjs";
import "element-plus/es/components/descriptions-item/style/css";
import { ElDialog } from "element-plus/es/components/dialog/index.mjs";
import "element-plus/es/components/dialog/style/css";
import { ElDrawer } from "element-plus/es/components/drawer/index.mjs";
import "element-plus/es/components/drawer/style/css";
import { ElDropdown } from "element-plus/es/components/dropdown/index.mjs";
import "element-plus/es/components/dropdown/style/css";
import "element-plus/es/components/dropdown-item/style/css";
import "element-plus/es/components/dropdown-menu/style/css";
import { ElDropdownItem, ElDropdownMenu } from "element-plus/es/components/dropdown/index.mjs";
import { ElEmpty } from "element-plus/es/components/empty/index.mjs";
import "element-plus/es/components/empty/style/css";
import { ElForm } from "element-plus/es/components/form/index.mjs";
import "element-plus/es/components/form/style/css";
import { ElFormItem } from "element-plus/es/components/form/index.mjs";
import "element-plus/es/components/form-item/style/css";
import { ElIcon } from "element-plus/es/components/icon/index.mjs";
import "element-plus/es/components/icon/style/css";
import { ElInput } from "element-plus/es/components/input/index.mjs";
import "element-plus/es/components/input/style/css";
import { ElInputNumber } from "element-plus/es/components/input-number/index.mjs";
import "element-plus/es/components/input-number/style/css";
import { ElMenu } from "element-plus/es/components/menu/index.mjs";
import "element-plus/es/components/menu/style/css";
import { ElMenuItem } from "element-plus/es/components/menu/index.mjs";
import "element-plus/es/components/menu-item/style/css";
import { ElOption } from "element-plus/es/components/select/index.mjs";
import "element-plus/es/components/option/style/css";
import { ElPagination } from "element-plus/es/components/pagination/index.mjs";
import "element-plus/es/components/pagination/style/css";
import { ElRadio } from "element-plus/es/components/radio/index.mjs";
import "element-plus/es/components/radio/style/css";
import { ElRadioButton } from "element-plus/es/components/radio/index.mjs";
import "element-plus/es/components/radio-button/style/css";
import { ElRadioGroup } from "element-plus/es/components/radio/index.mjs";
import "element-plus/es/components/radio-group/style/css";
import { ElSelect } from "element-plus/es/components/select/index.mjs";
import "element-plus/es/components/select/style/css";
import { ElSkeleton } from "element-plus/es/components/skeleton/index.mjs";
import "element-plus/es/components/skeleton/style/css";
import { ElSubMenu } from "element-plus/es/components/menu/index.mjs";
import "element-plus/es/components/sub-menu/style/css";
import { ElSwitch } from "element-plus/es/components/switch/index.mjs";
import "element-plus/es/components/switch/style/css";
import { ElTable } from "element-plus/es/components/table/index.mjs";
import "element-plus/es/components/table/style/css";
import { ElTableColumn } from "element-plus/es/components/table/index.mjs";
import "element-plus/es/components/table-column/style/css";
import { ElTabPane } from "element-plus/es/components/tabs/index.mjs";
import "element-plus/es/components/tab-pane/style/css";
import { ElTabs } from "element-plus/es/components/tabs/index.mjs";
import "element-plus/es/components/tabs/style/css";
import { ElTag } from "element-plus/es/components/tag/index.mjs";
import "element-plus/es/components/tag/style/css";
import { ElTimeline } from "element-plus/es/components/timeline/index.mjs";
import "element-plus/es/components/timeline/style/css";
import { ElTimelineItem } from "element-plus/es/components/timeline/index.mjs";
import "element-plus/es/components/timeline-item/style/css";

const components: Component[] = [
  ElAlert, ElBreadcrumb, ElBreadcrumbItem, ElButton, ElCard, ElCheckbox,
  ElCollapse, ElCollapseItem, ElDatePicker, ElDescriptions, ElDescriptionsItem,
  ElDialog, ElDrawer, ElDropdown, ElDropdownItem, ElDropdownMenu, ElEmpty,
  ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElMenu, ElMenuItem,
  ElOption, ElPagination, ElRadio, ElRadioButton, ElRadioGroup, ElSelect,
  ElSkeleton, ElSubMenu, ElSwitch, ElTable, ElTableColumn, ElTabPane, ElTabs,
  ElTag, ElTimeline, ElTimelineItem,
];

export function registerElementPlusComponents(app: App): void {
  for (const component of components) {
    if (component.name) app.component(component.name, component);
  }
}
