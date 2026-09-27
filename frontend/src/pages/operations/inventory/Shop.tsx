import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  Clock,
  Eye,
  EyeOff,
  Filter,
  Package,
  PackageCheck,
  Plus,
  RefreshCw,
  Search,
  ShoppingBag,
  ShoppingCart,
  Store,
  Tag,
  Trash2,
  Truck,
  X,
} from "lucide-react";
import {
  createShopItem,
  deleteShopItem,
  fulfillShopOrder,
  getAvailableCatalogItems,
  listShopItems,
  listShopOrders,
  updateShopItem,
} from "@/api/shop";
import { getWarehousesApi } from "@/api/inventory";
import type {
  CatalogItemAvailable,
  ShopItem,
  ShopItemCreateInput,
  ShopItemUpdateInput,
  ShopOrder,
} from "@/types/shop";

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export default function InventoryShop() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"products" | "orders">("products");

  // Filters
  const [productSearch, setProductSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [orderSearch, setOrderSearch] = useState("");
  const [orderStatusFilter, setOrderStatusFilter] = useState<string>("all");

  // Modals
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ShopItem | null>(null);
  const [breakdownItem, setBreakdownItem] = useState<ShopItem | null>(null);
  const [fulfillingOrder, setFulfillingOrder] = useState<ShopOrder | null>(null);
  const [fulfillWarehouseId, setFulfillWarehouseId] = useState("");
  const [fulfillNotes, setFulfillNotes] = useState("");

  // Queries
  const { data: shopItems = [], isLoading: isLoadingItems, refetch: refetchItems } = useQuery({
    queryKey: ["shop-items", productSearch, statusFilter],
    queryFn: () =>
      listShopItems({
        search: productSearch || undefined,
        is_published: statusFilter === "all" ? undefined : statusFilter === "published",
      }),
  });

  const { data: availableCatalog = [], isLoading: isLoadingCatalog } = useQuery({
    queryKey: ["available-catalog"],
    queryFn: () => getAvailableCatalogItems(),
    enabled: isAddModalOpen,
  });

  const { data: orders = [], isLoading: isLoadingOrders, refetch: refetchOrders } = useQuery({
    queryKey: ["shop-orders", orderSearch, orderStatusFilter],
    queryFn: () =>
      listShopOrders({
        search: orderSearch || undefined,
        status: orderStatusFilter === "all" ? undefined : orderStatusFilter,
      }),
  });

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inventory-warehouses"],
    queryFn: () => getWarehousesApi(undefined, false),
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: ShopItemCreateInput) => createShopItem(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shop-items"] });
      setIsAddModalOpen(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ShopItemUpdateInput }) =>
      updateShopItem(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shop-items"] });
      setEditingItem(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteShopItem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shop-items"] });
    },
  });

  const fulfillMutation = useMutation({
    mutationFn: ({ orderId, warehouseId, notes }: { orderId: string; warehouseId: string; notes?: string }) =>
      fulfillShopOrder(orderId, { warehouse_id: warehouseId, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shop-orders"] });
      queryClient.invalidateQueries({ queryKey: ["shop-items"] });
      setFulfillingOrder(null);
      setFulfillWarehouseId("");
      setFulfillNotes("");
    },
  });

  // Form State for Adding Item
  const [selectedCatalogItem, setSelectedCatalogItem] = useState<CatalogItemAvailable | null>(null);
  const [formData, setFormData] = useState({
    display_name: "",
    slug: "",
    subtitle: "",
    description: "",
    price_aed: "",
    compare_at_price_aed: "",
    cover_image_url: "",
    is_published: true,
    is_preorder_enabled: true,
    preorder_message: "Pre-order available — Estimated dispatch within 2-3 weeks",
  });

  const handleSelectCatalog = (catItem: CatalogItemAvailable) => {
    setSelectedCatalogItem(catItem);
    setFormData((prev) => ({
      ...prev,
      display_name: catItem.name,
      slug: slugify(catItem.name),
      subtitle: `${catItem.category.toUpperCase()} • Ground Station Equipment`,
    }));
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCatalogItem) return;

    createMutation.mutate({
      item_id: selectedCatalogItem.id,
      slug: formData.slug.trim().toLowerCase(),
      display_name: formData.display_name.trim(),
      subtitle: formData.subtitle.trim() || undefined,
      description: formData.description.trim() || undefined,
      price_aed: parseFloat(formData.price_aed) || 0,
      compare_at_price_aed: formData.compare_at_price_aed
        ? parseFloat(formData.compare_at_price_aed)
        : undefined,
      cover_image_url: formData.cover_image_url.trim() || undefined,
      is_published: formData.is_published,
      is_preorder_enabled: formData.is_preorder_enabled,
      preorder_message: formData.preorder_message,
    });
  };

  // Metrics calculations
  const totalPublished = shopItems.filter((i) => i.is_published).length;
  const inStockCount = shopItems.filter((i) => i.is_published && i.total_stock > 0).length;
  const preOrderCount = shopItems.filter((i) => i.is_published && i.total_stock === 0).length;
  const pendingOrdersCount = orders.filter((o) => o.status === "paid" || o.status === "pending_payment").length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <ShoppingBag className="w-6 h-6" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-white">Shop & Commerce</h1>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Publish catalogue items to the storefront, manage AED pricing, and track multi-warehouse inventory.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              refetchItems();
              refetchOrders();
            }}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 transition"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>

          <button
            onClick={() => {
              setSelectedCatalogItem(null);
              setFormData({
                display_name: "",
                slug: "",
                subtitle: "",
                description: "",
                price_aed: "",
                compare_at_price_aed: "",
                cover_image_url: "",
                is_published: true,
                is_preorder_enabled: true,
                preorder_message: "Pre-order available — Estimated dispatch within 2-3 weeks",
              });
              setIsAddModalOpen(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20 transition"
          >
            <Plus className="w-4 h-4" />
            Add Item to Shop
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Published Products</span>
            <Store className="w-4 h-4 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold mt-2 text-white">{totalPublished}</p>
          <span className="text-xs text-slate-500">Live on public shop</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Ready to Ship</span>
            <PackageCheck className="w-4 h-4 text-cyan-400" />
          </div>
          <p className="text-2xl font-bold mt-2 text-white">{inStockCount}</p>
          <span className="text-xs text-slate-500">Immediate fulfillment</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Pre-Order Active</span>
            <Clock className="w-4 h-4 text-amber-400" />
          </div>
          <p className="text-2xl font-bold mt-2 text-white">{preOrderCount}</p>
          <span className="text-xs text-slate-500">Stock = 0 in warehouses</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Orders Active</span>
            <ShoppingCart className="w-4 h-4 text-indigo-400" />
          </div>
          <p className="text-2xl font-bold mt-2 text-white">{orders.length}</p>
          <span className="text-xs text-slate-500">{pendingOrdersCount} pending / awaiting ship</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800">
        <button
          onClick={() => setActiveTab("products")}
          className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition ${
            activeTab === "products"
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <span className="flex items-center gap-2">
            <Tag className="w-4 h-4" />
            Products Catalog ({shopItems.length})
          </span>
        </button>

        <button
          onClick={() => setActiveTab("orders")}
          className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition ${
            activeTab === "orders"
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <span className="flex items-center gap-2">
            <Truck className="w-4 h-4" />
            Customer Orders & Pre-orders ({orders.length})
          </span>
        </button>
      </div>

      {/* TAB 1: SHOP PRODUCTS */}
      {activeTab === "products" && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="flex flex-col sm:flex-row gap-3 items-center justify-between bg-slate-900/50 p-3 rounded-lg border border-slate-800">
            <div className="relative w-full sm:w-72">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search products or slug..."
                value={productSearch}
                onChange={(e) => setProductSearch(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex items-center gap-3 w-full sm:w-auto">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Filter className="w-3.5 h-3.5" />
                <span>Filter:</span>
              </div>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                <option value="all">All Products</option>
                <option value="published">Published Only</option>
                <option value="unpublished">Unpublished Drafts</option>
              </select>
            </div>
          </div>

          {/* Products Table */}
          {isLoadingItems ? (
            <div className="p-12 text-center text-slate-500">Loading shop catalog...</div>
          ) : shopItems.length === 0 ? (
            <div className="p-12 text-center rounded-xl bg-slate-900/30 border border-slate-800/80">
              <Package className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-base font-medium text-slate-300">No shop products found</p>
              <p className="text-xs text-slate-500 mt-1">
                Add an item from your physical catalogue to make it purchasable on the store.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3">Product</th>
                    <th className="px-4 py-3">Price (AED)</th>
                    <th className="px-4 py-3">Total Stock</th>
                    <th className="px-4 py-3">Warehouse Breakdown</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {shopItems.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-800/30 transition">
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-3">
                          {item.cover_image_url ? (
                            <img
                              src={item.cover_image_url}
                              alt={item.display_name}
                              className="w-11 h-11 object-cover rounded-lg border border-slate-800 bg-slate-950 flex-shrink-0"
                            />
                          ) : (
                            <div className="w-11 h-11 rounded-lg border border-slate-800 bg-slate-950 flex items-center justify-center text-slate-600 flex-shrink-0">
                              <ShoppingBag className="w-5 h-5" />
                            </div>
                          )}
                          <div>
                            <div className="font-semibold text-slate-200">{item.display_name}</div>
                            <div className="text-xs text-slate-400 flex items-center gap-1.5 mt-0.5">
                              <span className="font-mono text-slate-500">/{item.slug}</span>
                              <span>•</span>
                              <span className="text-slate-500">{item.catalog_item_name}</span>
                            </div>
                          </div>
                        </div>
                      </td>

                      <td className="px-4 py-3.5">
                        <div className="font-semibold text-white">
                          AED {parseFloat(String(item.price_aed)).toLocaleString()}
                        </div>
                        {item.compare_at_price_aed && (
                          <div className="text-xs text-slate-500 line-through">
                            AED {parseFloat(String(item.compare_at_price_aed)).toLocaleString()}
                          </div>
                        )}
                      </td>

                      <td className="px-4 py-3.5">
                        {item.total_stock > 0 ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            {item.total_stock} in stock
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            <Clock className="w-3.5 h-3.5" />
                            Pre-order ({item.total_stock})
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3.5">
                        <button
                          onClick={() => setBreakdownItem(item)}
                          className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-medium bg-indigo-500/10 px-2.5 py-1 rounded-md border border-indigo-500/20 transition"
                        >
                          <Building2 className="w-3.5 h-3.5" />
                          {item.warehouse_breakdown.length} Warehouses / Resellers
                        </button>
                      </td>

                      <td className="px-4 py-3.5">
                        <button
                          onClick={() =>
                            updateMutation.mutate({
                              id: item.id,
                              data: { is_published: !item.is_published },
                            })
                          }
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border transition ${
                            item.is_published
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20"
                              : "bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700"
                          }`}
                        >
                          {item.is_published ? (
                            <>
                              <Eye className="w-3.5 h-3.5" /> Published
                            </>
                          ) : (
                            <>
                              <EyeOff className="w-3.5 h-3.5" /> Draft
                            </>
                          )}
                        </button>
                      </td>

                      <td className="px-4 py-3.5 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setEditingItem(item)}
                            className="px-2.5 py-1 text-xs rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => {
                              if (confirm(`Remove "${item.display_name}" from shop storefront?`)) {
                                deleteMutation.mutate(item.id);
                              }
                            }}
                            className="p-1 text-slate-500 hover:text-rose-400 transition"
                            title="Remove from shop"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: ORDERS & FULFILLMENT */}
      {activeTab === "orders" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 items-center justify-between bg-slate-900/50 p-3 rounded-lg border border-slate-800">
            <div className="relative w-full sm:w-80">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search order number or email..."
                value={orderSearch}
                onChange={(e) => setOrderSearch(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex items-center gap-3 w-full sm:w-auto">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Filter className="w-3.5 h-3.5" />
                <span>Status:</span>
              </div>
              <select
                value={orderStatusFilter}
                onChange={(e) => setOrderStatusFilter(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                <option value="all">All Orders</option>
                <option value="paid">Paid (Awaiting Fulfillment)</option>
                <option value="fulfilled">Fulfilled</option>
                <option value="pending_payment">Pending Payment</option>
              </select>
            </div>
          </div>

          {isLoadingOrders ? (
            <div className="p-12 text-center text-slate-500">Loading orders...</div>
          ) : orders.length === 0 ? (
            <div className="p-12 text-center rounded-xl bg-slate-900/30 border border-slate-800/80">
              <ShoppingCart className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-base font-medium text-slate-300">No orders recorded yet</p>
              <p className="text-xs text-slate-500 mt-1">
                Customer purchases made through Stripe will appear here with live fulfillment tracking.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3">Order Number</th>
                    <th className="px-4 py-3">Customer</th>
                    <th className="px-4 py-3">Items</th>
                    <th className="px-4 py-3">Total (AED)</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Payment</th>
                    <th className="px-4 py-3">Fulfillment</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {orders.map((order) => (
                    <tr key={order.id} className="hover:bg-slate-800/30 transition">
                      <td className="px-4 py-3.5">
                        <div className="font-mono font-semibold text-slate-200">{order.order_number}</div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {new Date(order.created_at).toLocaleDateString()}
                        </div>
                      </td>

                      <td className="px-4 py-3.5">
                        <div className="font-medium text-slate-300">{order.customer_name}</div>
                        <div className="text-xs text-slate-500">{order.customer_email}</div>
                      </td>

                      <td className="px-4 py-3.5">
                        <div className="text-xs text-slate-300 space-y-1">
                          {order.items.map((i) => (
                            <div key={i.id} className="flex items-center gap-1.5">
                              <span className="font-semibold text-slate-200">{i.quantity}x</span>
                              <span>{i.item_name}</span>
                              {i.is_preorder && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                  Pre-order
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </td>

                      <td className="px-4 py-3.5 font-semibold text-white">
                        AED {parseFloat(String(order.total_amount_aed)).toLocaleString()}
                      </td>

                      <td className="px-4 py-3.5">
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-medium ${
                            order.order_type === "pre_order"
                              ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              : order.order_type === "mixed"
                              ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                              : "bg-slate-800 text-slate-300"
                          }`}
                        >
                          {order.order_type.toUpperCase()}
                        </span>
                      </td>

                      <td className="px-4 py-3.5">
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-semibold ${
                            order.status === "paid" || order.status === "fulfilled"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          }`}
                        >
                          {order.status === "fulfilled" ? "PAID" : order.status.toUpperCase()}
                        </span>
                      </td>

                      <td className="px-4 py-3.5">
                        {order.status === "fulfilled" ? (
                          <div className="text-xs text-emerald-400 flex items-center gap-1.5">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>Fulfilled ({order.fulfilled_warehouse_name || "Warehouse"})</span>
                          </div>
                        ) : (
                          <span className="text-xs text-amber-400 flex items-center gap-1.5">
                            <Clock className="w-3.5 h-3.5" />
                            Awaiting Dispatch
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3.5 text-right">
                        {order.status !== "fulfilled" && (
                          <button
                            onClick={() => {
                              setFulfillingOrder(order);
                              setFulfillWarehouseId(warehouses[0]?.id || "");
                              setFulfillNotes("");
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition"
                          >
                            <PackageCheck className="w-3.5 h-3.5" />
                            Fulfill Order
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* MODAL 1: ADD ITEM TO SHOP */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl p-6 space-y-5 my-8">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center gap-2">
                <Plus className="w-5 h-5 text-indigo-400" />
                <h3 className="text-lg font-bold text-white">Add Catalogue Item to Shop</h3>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="text-slate-500 hover:text-slate-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Step 1: Select Catalogue Item */}
            {!selectedCatalogItem ? (
              <div className="space-y-4">
                <p className="text-sm text-slate-400">
                  Select an item from your physical catalogue. The shop will automatically track its
                  stock across all active warehouses and external resellers.
                </p>

                {isLoadingCatalog ? (
                  <div className="p-8 text-center text-slate-500">Loading catalog items...</div>
                ) : availableCatalog.length === 0 ? (
                  <div className="p-6 text-center rounded-lg bg-slate-950 border border-slate-800 text-slate-400 text-sm">
                    All catalogue items are already added to the shop!
                  </div>
                ) : (
                  <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
                    {availableCatalog.map((cat) => (
                      <div
                        key={cat.id}
                        onClick={() => handleSelectCatalog(cat)}
                        className="p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-indigo-500/50 hover:bg-slate-800/40 cursor-pointer flex items-center justify-between transition"
                      >
                        <div>
                          <div className="font-semibold text-slate-200">{cat.name}</div>
                          <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                            <span>SKU: {cat.code}</span>
                            <span>•</span>
                            <span className="uppercase">{cat.category}</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <span
                            className={`text-xs px-2 py-0.5 rounded font-medium ${
                              cat.total_stock > 0
                                ? "bg-emerald-500/10 text-emerald-400"
                                : "bg-amber-500/10 text-amber-400"
                            }`}
                          >
                            {cat.total_stock} in stock
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              /* Step 2: Commercial Configuration */
              <form onSubmit={handleCreateSubmit} className="space-y-4">
                <div className="p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-between">
                  <div>
                    <span className="text-xs text-indigo-400 font-semibold uppercase">Selected Catalogue Item</span>
                    <div className="text-sm font-bold text-white">{selectedCatalogItem.name}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedCatalogItem(null)}
                    className="text-xs text-indigo-300 hover:underline"
                  >
                    Change Item
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Display Name *</label>
                    <input
                      type="text"
                      required
                      value={formData.display_name}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          display_name: e.target.value,
                          slug: slugify(e.target.value),
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">URL Slug *</label>
                    <input
                      type="text"
                      required
                      value={formData.slug}
                      onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Retail Price (AED) *</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      placeholder="e.g. 450.00"
                      value={formData.price_aed}
                      onChange={(e) => setFormData({ ...formData, price_aed: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Compare at Price (AED) <span className="text-slate-500 font-normal">(Optional Strikethrough)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="e.g. 599.00"
                      value={formData.compare_at_price_aed}
                      onChange={(e) => setFormData({ ...formData, compare_at_price_aed: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Cover Image URL</label>
                  <input
                    type="url"
                    placeholder="https://... /product.jpg"
                    value={formData.cover_image_url}
                    onChange={(e) => setFormData({ ...formData, cover_image_url: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Short Tagline / Subtitle</label>
                  <input
                    type="text"
                    placeholder="e.g. Flight-Ready Ground Station Communication Kit"
                    value={formData.subtitle}
                    onChange={(e) => setFormData({ ...formData, subtitle: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Product Description</label>
                  <textarea
                    rows={3}
                    placeholder="Full product overview, contents, and technical specs..."
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="flex flex-col sm:flex-row gap-4 pt-2">
                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.is_published}
                      onChange={(e) => setFormData({ ...formData, is_published: e.target.checked })}
                      className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500"
                    />
                    Publish immediately to store
                  </label>

                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.is_preorder_enabled}
                      onChange={(e) => setFormData({ ...formData, is_preorder_enabled: e.target.checked })}
                      className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500"
                    />
                    Allow Pre-orders when out of stock
                  </label>
                </div>

                <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(false)}
                    className="px-4 py-2 text-sm rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createMutation.isPending}
                    className="px-5 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg disabled:opacity-50"
                  >
                    {createMutation.isPending ? "Adding..." : "Add to Shop"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* MODAL 2: WAREHOUSE BREAKDOWN */}
      {breakdownItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Building2 className="w-5 h-5 text-indigo-400" />
                <h3 className="text-base font-bold text-white">Warehouse Stock Breakdown</h3>
              </div>
              <button
                onClick={() => setBreakdownItem(null)}
                className="text-slate-500 hover:text-slate-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div>
              <div className="font-semibold text-slate-200">{breakdownItem.display_name}</div>
              <p className="text-xs text-slate-400 mt-0.5">
                Total aggregate inventory across all physical depots and reseller locations.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase text-slate-400">Total System Stock</span>
              <span
                className={`text-sm font-bold ${
                  breakdownItem.total_stock > 0 ? "text-emerald-400" : "text-amber-400"
                }`}
              >
                {breakdownItem.total_stock} Units ({breakdownItem.stock_status.toUpperCase()})
              </span>
            </div>

            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
              {breakdownItem.warehouse_breakdown.length === 0 ? (
                <div className="p-4 text-center text-xs text-slate-500 rounded bg-slate-950/60 border border-slate-800/60">
                  No warehouse currently holds loose stock for this item. Orders will automatically register as
                  Pre-orders.
                </div>
              ) : (
                breakdownItem.warehouse_breakdown.map((wh) => (
                  <div
                    key={wh.warehouse_id}
                    className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 flex items-center justify-between"
                  >
                    <div>
                      <div className="font-medium text-slate-200 text-sm">{wh.warehouse_name}</div>
                      {wh.warehouse_code && (
                        <div className="text-xs font-mono text-slate-500">{wh.warehouse_code}</div>
                      )}
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-bold text-emerald-400">{wh.qty} units</span>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setBreakdownItem(null)}
                className="px-4 py-2 text-sm rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: FULFILL ORDER */}
      {fulfillingOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <PackageCheck className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-bold text-white">Fulfill Order {fulfillingOrder.order_number}</h3>
              </div>
              <button
                onClick={() => setFulfillingOrder(null)}
                className="text-slate-500 hover:text-slate-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">Customer:</span>
                <span className="font-semibold text-slate-200">{fulfillingOrder.customer_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Total:</span>
                <span className="font-semibold text-slate-200">AED {fulfillingOrder.total_amount_aed}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Items:</span>
                <span className="text-slate-300">{fulfillingOrder.items.map((i) => `${i.quantity}x ${i.item_name}`).join(", ")}</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Fulfill from Warehouse / Reseller *
              </label>
              <select
                value={fulfillWarehouseId}
                onChange={(e) => setFulfillWarehouseId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                {warehouses.map((wh) => (
                  <option key={wh.id} value={wh.id}>
                    {wh.name} {wh.code ? `(${wh.code})` : ""}
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-slate-500 mt-1">
                Inventory stock levels will be automatically deducted from this warehouse and logged in the movement ledger.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Fulfillment / Tracking Notes (Optional)
              </label>
              <textarea
                rows={2}
                placeholder="e.g. Dispatched via Aramex Tracking #123456789"
                value={fulfillNotes}
                onChange={(e) => setFulfillNotes(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setFulfillingOrder(null)}
                className="px-4 py-2 text-sm rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={fulfillMutation.isPending || !fulfillWarehouseId}
                onClick={() =>
                  fulfillMutation.mutate({
                    orderId: fulfillingOrder.id,
                    warehouseId: fulfillWarehouseId,
                    notes: fulfillNotes.trim() || undefined,
                  })
                }
                className="px-5 py-2 text-sm font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg disabled:opacity-50"
              >
                {fulfillMutation.isPending ? "Fulfilling..." : "Confirm Dispatch"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: EDIT ITEM */}
      {editingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-xl p-6 space-y-4 my-8">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Tag className="w-5 h-5 text-indigo-400" />
                <h3 className="text-base font-bold text-white">Edit Shop Product</h3>
              </div>
              <button
                onClick={() => setEditingItem(null)}
                className="text-slate-500 hover:text-slate-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Display Name</label>
                <input
                  type="text"
                  value={editingItem.display_name}
                  onChange={(e) => setEditingItem({ ...editingItem, display_name: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Price (AED)</label>
                <input
                  type="number"
                  step="0.01"
                  value={editingItem.price_aed}
                  onChange={(e) => setEditingItem({ ...editingItem, price_aed: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Compare at Price (AED)</label>
                <input
                  type="number"
                  step="0.01"
                  value={editingItem.compare_at_price_aed || ""}
                  onChange={(e) => setEditingItem({ ...editingItem, compare_at_price_aed: e.target.value || null })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Cover Image URL</label>
                <input
                  type="url"
                  value={editingItem.cover_image_url || ""}
                  onChange={(e) => setEditingItem({ ...editingItem, cover_image_url: e.target.value || null })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Subtitle</label>
              <input
                type="text"
                value={editingItem.subtitle || ""}
                onChange={(e) => setEditingItem({ ...editingItem, subtitle: e.target.value || null })}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Description</label>
              <textarea
                rows={3}
                value={editingItem.description || ""}
                onChange={(e) => setEditingItem({ ...editingItem, description: e.target.value || null })}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex flex-col sm:flex-row gap-4 pt-2">
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editingItem.is_published}
                  onChange={(e) => setEditingItem({ ...editingItem, is_published: e.target.checked })}
                  className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500"
                />
                Published
              </label>

              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editingItem.is_preorder_enabled}
                  onChange={(e) => setEditingItem({ ...editingItem, is_preorder_enabled: e.target.checked })}
                  className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500"
                />
                Allow Pre-order
              </label>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setEditingItem(null)}
                className="px-4 py-2 text-sm rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={updateMutation.isPending}
                onClick={() =>
                  updateMutation.mutate({
                    id: editingItem.id,
                    data: {
                      display_name: editingItem.display_name,
                      subtitle: editingItem.subtitle,
                      description: editingItem.description,
                      price_aed: parseFloat(String(editingItem.price_aed)) || 0,
                      compare_at_price_aed: editingItem.compare_at_price_aed
                        ? parseFloat(String(editingItem.compare_at_price_aed))
                        : null,
                      cover_image_url: editingItem.cover_image_url,
                      is_published: editingItem.is_published,
                      is_preorder_enabled: editingItem.is_preorder_enabled,
                    },
                  })
                }
                className="px-5 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg disabled:opacity-50"
              >
                {updateMutation.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
