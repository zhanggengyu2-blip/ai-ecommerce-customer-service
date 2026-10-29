<script setup lang="ts">
import { roleRows } from "../../domain/roles";
</script>
<template>
  <el-card shadow="never"
    ><template #header>内置角色与权限</template
    ><el-table :data="roleRows" border stripe
      ><el-table-column prop="name" label="角色" width="150" /><el-table-column
        prop="role"
        label="标识"
        width="220" /><el-table-column
        prop="permissions"
        label="权限范围"
        min-width="300"
    /></el-table>
    <p class="list-note">
      角色在用户管理中调整；接口在服务端校验权限。
    </p></el-card
  >
</template>
