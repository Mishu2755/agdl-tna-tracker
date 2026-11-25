import os
import io
import json
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file, redirect, url_for, Response, session

from erp_client import ERPClient
from storage import TNAStorage
from task_engine import generate_style_tasks, is_task_completed, sort_tasks, CATEGORY_ORDER
from report_generator import generate_excel_report, generate_pdf_report

app = Flask(__name__)
app.secret_key = "agdl_tna_tracker_secret_key"

BASE_DIR = Path(__file__).resolve().parent
storage = TNAStorage(BASE_DIR / "tna_data.json")
erp = ERPClient()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AGDL T&A Tracker</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; }
        .custom-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scroll::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        textarea.auto-expand {
            resize: vertical;
            min-height: 32px;
            overflow-y: hidden;
            line-height: 1.35;
        }
    </style>
</head>
<body class="bg-slate-100 text-slate-800 min-h-screen flex flex-col w-full">

    <!-- Top Navigation Bar (Full Width Edge-to-Edge) -->
    <header id="topHeader" class="bg-slate-900 text-white shadow-md sticky top-0 z-50 w-full">
        <div class="w-full px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center font-bold text-xl shadow-inner tracking-wider">
                    <i class="fa-solid fa-clipboard-check"></i>
                </div>
                <div>
                    <h1 class="font-bold text-lg leading-tight flex items-center space-x-2">
                        <span>AGDL T&A Tracker</span>
                        <span class="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full font-semibold">Live ERP</span>
                    </h1>
                    <p class="text-[11px] text-slate-400">Aman Graphics & Designs Ltd. - Merchandising Management System</p>
                </div>
            </div>

            <div class="flex items-center space-x-3">
                <!-- Buyer Selector -->
                <div class="flex items-center space-x-2 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700">
                    <i class="fa-solid fa-user-tag text-blue-400 text-xs"></i>
                    <select id="buyerSelect" onchange="changeBuyer(this.value)" class="bg-transparent text-xs font-semibold text-white focus:outline-none cursor-pointer">
                        <option value="ALL" class="bg-slate-800 text-white" {% if current_buyer.code == 'ALL' %}selected{% endif %}>
                            -- All Buyers --
                        </option>
                        {% for b in buyers %}
                        <option value="{{ b.code }}" class="bg-slate-800 text-white" {% if b.code == current_buyer.code %}selected{% endif %}>
                            {{ b.name }}
                        </option>
                        {% endfor %}
                    </select>
                </div>

                <!-- Export Excel -->
                <a href="/export/excel?buyer={{ current_buyer.code }}" class="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center space-x-1.5 shadow transition">
                    <i class="fa-solid fa-file-excel text-sm"></i>
                    <span>Export Excel</span>
                </a>

                <!-- Export PDF (A4 Full Width) -->
                <a href="/export/pdf?buyer={{ current_buyer.code }}" target="_blank" class="bg-red-600 hover:bg-red-500 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center space-x-1.5 shadow transition">
                    <i class="fa-solid fa-file-pdf text-sm"></i>
                    <span>A4 PDF Report</span>
                </a>
            </div>
        </div>
    </header>

    <!-- Main Content Container (Full Width 100% Responsive) -->
    <main class="w-full px-3 sm:px-5 lg:px-6 py-4 flex-1 space-y-4">

        <!-- Action & Status Toolbar -->
        <div class="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center justify-between gap-3 w-full">
            <div class="flex flex-wrap items-center gap-2.5">
                <!-- Sync Inhouse Button -->
                <button onclick="startSyncInhoused()" id="btnSync" class="bg-blue-600 hover:bg-blue-700 text-white px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center space-x-2 shadow-sm transition">
                    <i class="fa-solid fa-arrows-rotate" id="syncIcon"></i>
                    <span>Sync Inhoused with ERP</span>
                </button>

                <!-- Check & Add New Styles Button -->
                <button onclick="startCheckAddNewStyles()" id="btnAddStyles" class="bg-amber-600 hover:bg-amber-700 text-white px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center space-x-2 shadow-sm transition">
                    <i class="fa-solid fa-cloud-arrow-down" id="addIcon"></i>
                    <span>Check & Add Running Style from ERP</span>
                </button>

                <!-- Add Style Manually -->
                <button onclick="openManualStyleModal()" class="bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-2 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition border border-slate-300">
                    <i class="fa-solid fa-plus text-slate-500"></i>
                    <span>Add Style Manually</span>
                </button>

                <!-- Toggle Completed / Inhoused Items Filter -->
                <label class="flex items-center space-x-2 cursor-pointer bg-slate-50 px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 transition">
                    <input type="checkbox" id="hideCompletedCheck" onchange="toggleCompletedFilter(this.checked)" class="rounded text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 cursor-pointer" checked>
                    <span class="text-xs font-medium text-slate-600 select-none">Hide Fully Inhoused / Closed Tasks</span>
                </label>
            </div>

            <!-- Summary KPI Badges -->
            <div class="flex items-center space-x-4">
                <div class="text-right">
                    <div class="text-[10px] text-slate-400 font-medium uppercase tracking-wider">Running Styles</div>
                    <div class="text-base font-bold text-slate-800">{{ total_styles }}</div>
                </div>
                <div class="h-6 w-px bg-slate-200"></div>
                <div class="text-right">
                    <div class="text-[10px] text-slate-400 font-medium uppercase tracking-wider">Pending Tasks</div>
                    <div class="text-base font-bold text-amber-600">{{ pending_count }}</div>
                </div>
                <div class="h-6 w-px bg-slate-200"></div>
                <div class="text-right">
                    <div class="text-[10px] text-slate-400 font-medium uppercase tracking-wider">Inhoused / Closed</div>
                    <div class="text-base font-bold text-emerald-600">{{ closed_count }}</div>
                </div>
            </div>
        </div>

        <!-- Live Progress Bar Section (Visible during Sync / Check operations) -->
        <div id="progressSection" class="bg-white p-3.5 rounded-xl shadow-sm border border-blue-200 hidden w-full transition">
            <div class="flex items-center justify-between text-xs font-semibold mb-1.5">
                <span id="progressMessage" class="text-blue-700 flex items-center space-x-2">
                    <i class="fa-solid fa-circle-notch fa-spin"></i>
                    <span>Processing ERP data...</span>
                </span>
                <span id="progressPercent" class="text-blue-900 font-mono">0%</span>
            </div>
            <div class="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden border border-slate-200">
                <div id="progressBar" class="bg-blue-600 h-2.5 rounded-full transition-all duration-300 w-0"></div>
            </div>
        </div>

        <!-- Frozen Single-Line Filter & Bulk Action Toolbar (Sticky right below Header) -->
        <div id="stickyFilterToolbar" class="sticky top-16 z-40 bg-slate-100/95 backdrop-blur-sm pt-1 pb-1.5 -mt-1 space-y-1.5 w-full">
            <div class="bg-white px-3 py-2 rounded-xl border border-slate-200 shadow-sm flex flex-wrap lg:flex-nowrap items-center justify-between gap-2 w-full">
                <!-- Left: 3 Multi-Select Searchable Filters (Category, Style, Item) + Expand/Collapse -->
                <div class="flex flex-wrap md:flex-nowrap items-center gap-2 min-w-0">
                    <!-- Category Multi-Select Searchable Dropdown -->
                    <div class="relative" id="categoryFilterDropdownWrap">
                        <div class="flex items-center bg-slate-50 border border-slate-300 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20 rounded-lg px-2 py-1 transition w-40 sm:w-44">
                            <i class="fa-solid fa-layer-group text-indigo-500 text-[11px] mr-1.5 shrink-0"></i>
                            <input type="text" id="categorySearchInput"
                                placeholder="Filter Category..."
                                onfocus="openMultiDropdown('category')"
                                oninput="onMultiSearchInput('category', this.value)"
                                onkeydown="if(event.key==='Escape') closeAllMultiDropdowns()"
                                autocomplete="off"
                                class="bg-transparent text-xs text-slate-800 placeholder-slate-400 focus:outline-none w-full min-w-0">
                            <span id="categoryFilterCount" class="hidden ml-1 bg-indigo-600 text-white text-[10px] font-bold px-1.5 py-0.2 rounded-full shrink-0">0</span>
                            <button type="button" id="categoryFilterClearBtn" onclick="clearMultiFilter('category')" title="Clear Category Filter" class="hidden ml-1 text-slate-400 hover:text-red-500 text-xs px-0.5 shrink-0">
                                <i class="fa-solid fa-xmark"></i>
                            </button>
                            <button type="button" onclick="toggleMultiDropdown('category')" class="ml-0.5 text-slate-400 hover:text-slate-600 text-[10px] px-0.5 shrink-0" title="Show Category List">
                                <i class="fa-solid fa-chevron-down"></i>
                            </button>
                        </div>
                        <div id="categoryDropdownPanel" class="hidden absolute left-0 mt-1 w-60 bg-white border border-slate-200 rounded-xl shadow-xl z-50 overflow-hidden">
                            <div class="bg-slate-50 px-3 py-2 border-b border-slate-200 flex items-center justify-between text-[11px]">
                                <span class="font-semibold text-slate-600">Categories (<span id="categoryMatchCount">{{ category_options|length }}</span>)</span>
                                <div class="space-x-2">
                                    <button type="button" onclick="selectAllMatchingMulti('category')" class="text-indigo-600 hover:underline font-semibold">Select Matching</button>
                                    <button type="button" onclick="clearMultiFilter('category')" class="text-slate-500 hover:text-red-600 font-medium">Clear</button>
                                </div>
                            </div>
                            <div id="categoryDropdownList" class="max-h-56 overflow-y-auto custom-scroll divide-y divide-slate-100 p-1">
                                {% for cat in category_options %}
                                <label class="multi-opt-category flex items-center space-x-2 px-2.5 py-1.5 rounded-lg hover:bg-indigo-50/70 cursor-pointer text-xs text-slate-700" data-label="{{ cat|lower }}">
                                    <input type="checkbox" value="{{ cat|lower }}" data-display="{{ cat }}" onchange="onMultiCheckboxChange('category', this)" class="multi-cb-category rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5 shrink-0">
                                    <span class="truncate font-medium" title="{{ cat }}">{{ cat }}</span>
                                </label>
                                {% endfor %}
                            </div>
                        </div>
                    </div>

                    <!-- Style Multi-Select Searchable Dropdown -->
                    <div class="relative" id="styleFilterDropdownWrap">
                        <div class="flex items-center bg-slate-50 border border-slate-300 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 rounded-lg px-2 py-1 transition w-44 sm:w-48 xl:w-56">
                            <i class="fa-solid fa-shirt text-blue-500 text-[11px] mr-1.5 shrink-0"></i>
                            <input type="text" id="styleSearchInput"
                                placeholder="Filter Styles (849, JPA)..."
                                onfocus="openMultiDropdown('style')"
                                oninput="onMultiSearchInput('style', this.value)"
                                onkeydown="if(event.key==='Escape') closeAllMultiDropdowns()"
                                autocomplete="off"
                                class="bg-transparent text-xs text-slate-800 placeholder-slate-400 focus:outline-none w-full min-w-0">
                            <span id="styleFilterCount" class="hidden ml-1 bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.2 rounded-full shrink-0">0</span>
                            <button type="button" id="styleFilterClearBtn" onclick="clearMultiFilter('style')" title="Clear Style Filter" class="hidden ml-1 text-slate-400 hover:text-red-500 text-xs px-0.5 shrink-0">
                                <i class="fa-solid fa-xmark"></i>
                            </button>
                            <button type="button" onclick="toggleMultiDropdown('style')" class="ml-0.5 text-slate-400 hover:text-slate-600 text-[10px] px-0.5 shrink-0" title="Show Style List">
                                <i class="fa-solid fa-chevron-down"></i>
                            </button>
                        </div>
                        <div id="styleDropdownPanel" class="hidden absolute left-0 mt-1 w-72 sm:w-80 bg-white border border-slate-200 rounded-xl shadow-xl z-50 overflow-hidden">
                            <div class="bg-slate-50 px-3 py-2 border-b border-slate-200 flex items-center justify-between text-[11px]">
                                <span class="font-semibold text-slate-600">Select Styles (<span id="styleMatchCount">{{ style_options|length }}</span>)</span>
                                <div class="space-x-2">
                                    <button type="button" onclick="selectAllMatchingMulti('style')" class="text-blue-600 hover:underline font-semibold">Select Matching</button>
                                    <button type="button" onclick="clearMultiFilter('style')" class="text-slate-500 hover:text-red-600 font-medium">Clear</button>
                                </div>
                            </div>
                            <div id="styleDropdownList" class="max-h-64 overflow-y-auto custom-scroll divide-y divide-slate-100 p-1">
                                {% for st in style_options %}
                                <label class="multi-opt-style flex items-center space-x-2 px-2.5 py-1.5 rounded-lg hover:bg-blue-50/70 cursor-pointer text-xs text-slate-700" data-label="{{ st.name|lower }}">
                                    <input type="checkbox" value="{{ st.id }}" data-display="{{ st.name }}" onchange="onMultiCheckboxChange('style', this)" class="multi-cb-style rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 shrink-0">
                                    <span class="truncate font-medium" title="{{ st.name }}">{{ st.name }}</span>
                                </label>
                                {% endfor %}
                            </div>
                        </div>
                    </div>

                    <!-- Item Multi-Select Searchable Dropdown -->
                    <div class="relative" id="itemFilterDropdownWrap">
                        <div class="flex items-center bg-slate-50 border border-slate-300 focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-500/20 rounded-lg px-2 py-1 transition w-44 sm:w-48 xl:w-56">
                            <i class="fa-solid fa-tags text-emerald-600 text-[11px] mr-1.5 shrink-0"></i>
                            <input type="text" id="itemSearchInput"
                                placeholder="Filter Items (Label, Fabric)..."
                                onfocus="openMultiDropdown('item')"
                                oninput="onMultiSearchInput('item', this.value)"
                                onkeydown="if(event.key==='Escape') closeAllMultiDropdowns()"
                                autocomplete="off"
                                class="bg-transparent text-xs text-slate-800 placeholder-slate-400 focus:outline-none w-full min-w-0">
                            <span id="itemFilterCount" class="hidden ml-1 bg-emerald-600 text-white text-[10px] font-bold px-1.5 py-0.2 rounded-full shrink-0">0</span>
                            <button type="button" id="itemFilterClearBtn" onclick="clearMultiFilter('item')" title="Clear Item Filter" class="hidden ml-1 text-slate-400 hover:text-red-500 text-xs px-0.5 shrink-0">
                                <i class="fa-solid fa-xmark"></i>
                            </button>
                            <button type="button" onclick="toggleMultiDropdown('item')" class="ml-0.5 text-slate-400 hover:text-slate-600 text-[10px] px-0.5 shrink-0" title="Show Item List">
                                <i class="fa-solid fa-chevron-down"></i>
                            </button>
                        </div>
                        <div id="itemDropdownPanel" class="hidden absolute left-0 sm:right-0 sm:left-auto mt-1 w-72 sm:w-80 bg-white border border-slate-200 rounded-xl shadow-xl z-50 overflow-hidden">
                            <div class="bg-slate-50 px-3 py-2 border-b border-slate-200 flex items-center justify-between text-[11px]">
                                <span class="font-semibold text-slate-600">Select Items (<span id="itemMatchCount">{{ unique_items|length }}</span>)</span>
                                <div class="space-x-2">
                                    <button type="button" onclick="selectAllMatchingMulti('item')" class="text-emerald-600 hover:underline font-semibold">Select Matching</button>
                                    <button type="button" onclick="clearMultiFilter('item')" class="text-slate-500 hover:text-red-600 font-medium">Clear</button>
                                </div>
                            </div>
                            <div id="itemDropdownList" class="max-h-64 overflow-y-auto custom-scroll divide-y divide-slate-100 p-1">
                                {% for item in unique_items %}
                                <label class="multi-opt-item flex items-center space-x-2 px-2.5 py-1.5 rounded-lg hover:bg-emerald-50/70 cursor-pointer text-xs text-slate-700" data-label="{{ item|lower }}">
                                    <input type="checkbox" value="{{ item|lower }}" data-display="{{ item }}" onchange="onMultiCheckboxChange('item', this)" class="multi-cb-item rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 w-3.5 h-3.5 shrink-0">
                                    <span class="truncate font-medium" title="{{ item }}">{{ item }}</span>
                                </label>
                                {% endfor %}
                            </div>
                        </div>
                    </div>

                    <div class="flex items-center space-x-1 whitespace-nowrap shrink-0 pl-1">
                        <button onclick="expandAllStyles(true)" class="text-xs text-blue-600 hover:underline px-1 py-0.5 font-medium">Expand All</button>
                        <span class="text-slate-300">|</span>
                        <button onclick="expandAllStyles(false)" class="text-xs text-slate-500 hover:underline px-1 py-0.5 font-medium">Collapse All</button>
                    </div>
                </div>

                <!-- Right: Bulk Action for Selected Items & Selection Controls -->
                <div class="flex items-center gap-2 whitespace-nowrap shrink-0">
                    <button id="bulkActionBtn" onclick="openBulkActionModal()" disabled class="bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center space-x-1.5 shadow-sm transition">
                        <i class="fa-solid fa-list-check"></i>
                        <span>Action for Selected Items</span>
                        <span id="selectedCountBadge" class="hidden bg-white text-indigo-700 font-bold px-1.5 py-0.2 rounded-full text-[10px]">0</span>
                    </button>
                    <button onclick="toggleSelectAllVisible()" id="btnSelectAllVisible" class="text-xs text-indigo-600 hover:text-indigo-800 font-semibold px-1.5 py-1 rounded hover:bg-indigo-50 transition">
                        Select All Visible
                    </button>
                    <button onclick="clearAllSelections()" id="btnClearSelections" class="hidden text-xs text-slate-500 hover:text-red-600 font-medium px-1.5 py-1 rounded hover:bg-red-50 transition">
                        Clear Selection
                    </button>
                </div>
            </div>

            <!-- Active Filter Chips Strip (Hidden when no multi-filter chips active) -->
            <div id="activeFilterChipsBar" class="hidden bg-white px-3 py-1.5 rounded-xl border border-blue-200 shadow-sm flex flex-wrap items-center gap-1.5 w-full">
                <span class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mr-1">Active Filters:</span>
                <div id="activeFilterChipsList" class="flex flex-wrap items-center gap-1.5"></div>
                <button type="button" onclick="resetAllMultiFilters()" class="ml-auto text-[11px] text-red-600 hover:underline font-semibold px-2 py-0.5">
                    Reset All Filters
                </button>
            </div>
        </div>

        <!-- Styles & T&A Board (100% Full Width) -->
        <div class="space-y-3.5 w-full" id="stylesContainer">
            {% if styles|length == 0 %}
            <div class="bg-white rounded-xl p-10 text-center border border-dashed border-slate-300 w-full">
                <div class="w-14 h-14 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mx-auto mb-3 text-2xl">
                    <i class="fa-solid fa-folder-open"></i>
                </div>
                <h3 class="text-base font-bold text-slate-800">No Running Styles in Chart</h3>
                <p class="text-xs text-slate-500 max-w-md mx-auto mt-1 mb-5">
                    Click "Check & Add Running Style from ERP" to pull only genuine running styles where the last FFD PO shipment is pending for <strong>{{ current_buyer.name }}</strong>.
                </p>
                <button onclick="startCheckAddNewStyles()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-xs font-semibold inline-flex items-center space-x-2 shadow">
                    <i class="fa-solid fa-cloud-arrow-down"></i>
                    <span>Pull Running Styles from ERP</span>
                </button>
            </div>
            {% endif %}

            {% for style_id, s in styles.items() %}
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden transition-all duration-200 style-card w-full" id="card_{{ style_id }}" data-style-id="{{ style_id }}" data-style-name="{{ (s.style_name or style_id)|lower }}">
                <!-- Accordion Header: Click to expand / collapse style -->
                <div onclick="toggleStyleAccordion('{{ style_id }}')" class="bg-slate-50/95 hover:bg-slate-100/90 px-4 sm:px-6 py-3 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 cursor-pointer select-none transition">
                    <div class="flex items-center space-x-3">
                        <i class="fa-solid fa-chevron-down text-slate-400 text-xs transition transform duration-200 accordion-arrow" id="arrow_{{ style_id }}"></i>
                        <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                        <div>
                            <div class="flex flex-wrap items-center gap-2">
                                <h3 class="font-bold text-sm text-slate-900">{{ s.style_name }}</h3>
                                <span class="bg-blue-100 text-blue-700 text-[10px] px-2 py-0.5 rounded font-semibold">{{ s.garment_type or 'Garment' }}</span>
                                <span class="text-[11px] text-slate-500 font-medium">Order Qty: <strong class="text-slate-800">{{ "{:,}".format(s.garment_qty|int) }} Pcs</strong></span>
                                {% if s.fob %}<span class="text-[11px] text-slate-500">FOB: <strong class="text-slate-800">${{ s.fob }}</strong></span>{% endif %}
                            </div>

                            <!-- 4 Key Dates Row under Style Name -->
                            <div class="text-[11px] text-slate-600 mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
                                <span class="inline-flex items-center space-x-1">
                                    <i class="fa-regular fa-calendar-check text-indigo-500"></i>
                                    <span>OC Date: <strong class="text-slate-800">{{ s.oc_date or 'N/A' }}</strong></span>
                                </span>
                                <span class="inline-flex items-center space-x-1">
                                    <i class="fa-solid fa-plane-departure text-blue-500"></i>
                                    <span>1st FFD: <strong class="text-slate-800">{{ s.first_ffd or 'N/A' }}</strong></span>
                                </span>
                                <span class="inline-flex items-center space-x-1">
                                    <i class="fa-solid fa-truck-fast text-amber-500"></i>
                                    <span>Last FFD: <strong class="text-amber-800 font-bold">{{ s.last_ffd or 'N/A' }}</strong></span>
                                </span>
                                <span class="inline-flex items-center space-x-1">
                                    <i class="fa-solid fa-boxes-packing text-emerald-600"></i>
                                    <span>1st T&A Date (Fabric IH): <strong class="text-emerald-800">{{ s.first_tna_date or 'N/A' }}</strong></span>
                                </span>
                            </div>
                        </div>
                    </div>

                    <div class="flex items-center space-x-2" onclick="event.stopPropagation()">
                        <!-- Add Custom Task -->
                        <button onclick="openAddTaskModal('{{ style_id }}', '{{ s.style_name }}')" class="text-[11px] bg-white hover:bg-slate-100 text-slate-700 font-medium px-2.5 py-1 rounded-lg border border-slate-200 shadow-sm transition">
                            <i class="fa-solid fa-plus text-blue-500 mr-1"></i> Add Task
                        </button>

                        <!-- Remove Style -->
                        <button onclick="deleteStyle('{{ style_id }}', '{{ s.style_name }}')" class="text-[11px] text-red-500 hover:text-red-700 p-1.5 rounded hover:bg-red-50 transition" title="Remove Style">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>

                <!-- T&A Table Container (Accordion Body) -->
                <div class="overflow-x-auto custom-scroll accordion-body w-full" id="body_{{ style_id }}">
                    <table class="w-full text-left text-xs border-collapse table-fixed">
                        <thead>
                            <tr class="bg-slate-100/90 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[10px]">
                                <th class="py-2.5 px-2 w-[35px] text-center">
                                    <input type="checkbox" title="Select/Deselect all visible items in this style" onchange="toggleSelectStyleItems('{{ style_id }}', this.checked)" class="style-select-all rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5 cursor-pointer">
                                </th>
                                <th class="py-2.5 px-3 w-[100px]">Category</th>
                                <th class="py-2.5 px-3 w-[155px]">Item / Event</th>
                                <th class="py-2.5 px-3 w-[33%]">Latest Status / Update Note</th>
                                <th class="py-2.5 px-3 w-[24%]">Task / Action Note</th>
                                <th class="py-2.5 px-2 w-[70px] text-right">Book Qty</th>
                                <th class="py-2.5 px-2 w-[70px] text-right">I/H Qty</th>
                                <th class="py-2.5 px-2 w-[70px] text-right">Bal Qty</th>
                                <th class="py-2.5 px-2 w-[95px] text-center">Color Approval</th>
                                <th class="py-2.5 px-2 w-[85px] text-center">Status</th>
                                <th class="py-2.5 px-1 w-[35px] text-center">Del</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for t in s.tasks %}
                            {% set is_closed = (t.status|lower in ['closed', 'approved', 'done', 'completed']) or (t.booked_qty|float > 0 and t.bal_qty|float <= 0 and t.ih_qty|float > 0) %}
                            {% set is_pending_action = not is_closed and (t.bal_qty|float > 0 or t.status == 'Pending' or t.status == 'In Progress') %}
                            <tr class="transition task-row 
                                {% if is_closed %}is-closed-task bg-emerald-50/20 hover:bg-emerald-50/40
                                {% elif is_pending_action and t.category == 'Fabric' %}bg-sky-50/40 hover:bg-sky-50/70
                                {% elif is_pending_action and t.category == 'Sewing Accs' %}bg-purple-50/30 hover:bg-purple-50/60
                                {% elif is_pending_action and t.category == 'Finishing Accs' %}bg-amber-50/30 hover:bg-amber-50/60
                                {% elif is_pending_action %}bg-amber-50/20 hover:bg-amber-50/50
                                {% else %}hover:bg-slate-50/90{% endif %}" 
                                id="row_{{ style_id }}_{{ t.id }}" 
                                data-style-id="{{ style_id }}"
                                data-category="{{ t.category }}" 
                                data-item-name="{{ t.item_name|lower }}">
                                <td class="py-2 px-2 align-top text-center pt-2.5">
                                    <input type="checkbox" class="task-select-cb rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5 cursor-pointer" 
                                        data-style-id="{{ style_id }}" data-task-id="{{ t.id }}" 
                                        onchange="onTaskSelectChange(this)">
                                </td>
                                <td class="py-2 px-3 align-top">
                                    <span class="inline-block px-2 py-0.5 rounded text-[10px] font-semibold 
                                        {% if t.category == 'Basic' %}bg-blue-50 text-blue-700 border border-blue-200
                                        {% elif t.category == 'Fabric' %}bg-emerald-50 text-emerald-700 border border-emerald-200
                                        {% elif t.category == 'Sewing Accs' %}bg-purple-50 text-purple-700 border border-purple-200
                                        {% elif t.category == 'Finishing Accs' %}bg-amber-50 text-amber-700 border border-amber-200
                                        {% else %}bg-slate-100 text-slate-700 border border-slate-200{% endif %}">
                                        {{ t.category }}
                                    </span>
                                </td>
                                <td class="py-2 px-3 align-top font-semibold text-slate-800 break-words">
                                    {{ t.item_name }}
                                </td>
                                <td class="py-2 px-3 align-top">
                                    <textarea data-field="updates" oninput="autoExpandTextarea(this)" 
                                        onblur="saveField('{{ style_id }}', '{{ t.id }}', 'updates', this.value)" 
                                        class="auto-expand w-full bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-blue-500 p-1.5 rounded text-xs transition focus:outline-none text-slate-700" 
                                        rows="1">{{ t.updates }}</textarea>
                                </td>
                                <td class="py-2 px-3 align-top">
                                    <textarea data-field="task_notes" oninput="autoExpandTextarea(this)" 
                                        onblur="saveField('{{ style_id }}', '{{ t.id }}', 'task_notes', this.value)" 
                                        class="auto-expand w-full bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-blue-500 p-1.5 rounded text-xs transition focus:outline-none text-slate-600" 
                                        placeholder="Add notes..."
                                        rows="1">{{ '' if (t.task_notes == '0' or not t.task_notes) else t.task_notes }}</textarea>
                                </td>
                                <td class="py-2 px-2 align-top text-right font-mono font-medium text-slate-700 text-[11px]">
                                    {% if t.booked_qty|float > 0 %}{{ "{:g}".format(t.booked_qty|float) }} {{ t.uom }}{% else %}-{% endif %}
                                </td>
                                <td class="py-2 px-2 align-top text-right font-mono font-medium text-emerald-600 text-[11px]">
                                    {% if t.ih_qty|float > 0 %}{{ "{:g}".format(t.ih_qty|float) }} {{ t.uom }}{% else %}0{% endif %}
                                </td>
                                <td class="py-2 px-2 align-top text-right font-mono font-bold {% if t.bal_qty|float > 0 %}text-red-500{% else %}text-slate-400{% endif %} text-[11px]">
                                    {% if t.bal_qty|float > 0 %}{{ "{:g}".format(t.bal_qty|float) }} {{ t.uom }}{% else %}0{% endif %}
                                </td>
                                <!-- Editable Color Approval Field -->
                                <td class="py-2 px-2 align-top text-center">
                                    <input type="text" data-field="color_approval" value="{{ t.color_approval or 'Pending' }}" 
                                        onblur="saveField('{{ style_id }}', '{{ t.id }}', 'color_approval', this.value)" 
                                        class="w-full text-center bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-blue-500 px-1 py-0.5 rounded text-[11px] font-medium text-slate-700 focus:outline-none">
                                </td>
                                <td class="py-2 px-2 align-top text-center">
                                    <select data-field="status" onchange="saveField('{{ style_id }}', '{{ t.id }}', 'status', this.value)" 
                                        class="text-[10px] font-semibold rounded px-1.5 py-0.5 border cursor-pointer focus:outline-none 
                                        {% if is_closed %}bg-emerald-100 text-emerald-800 border-emerald-300
                                        {% elif t.status == 'In Progress' %}bg-amber-100 text-amber-800 border-amber-300
                                        {% else %}bg-slate-100 text-slate-700 border-slate-300{% endif %}">
                                        <option value="Pending" {% if t.status == 'Pending' %}selected{% endif %}>Pending</option>
                                        <option value="In Progress" {% if t.status == 'In Progress' %}selected{% endif %}>In Progress</option>
                                        <option value="Approved" {% if t.status == 'Approved' %}selected{% endif %}>Approved</option>
                                        <option value="Closed" {% if t.status == 'Closed' %}selected{% endif %}>Closed</option>
                                        <option value="Done" {% if t.status == 'Done' %}selected{% endif %}>Done</option>
                                    </select>
                                </td>
                                <td class="py-2 px-1 align-top text-center">
                                    <button onclick="deleteTask('{{ style_id }}', '{{ t.id }}')" class="text-slate-400 hover:text-red-500 p-1 transition" title="Delete Task">
                                        <i class="fa-solid fa-times"></i>
                                    </button>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endfor %}
        </div>
    </main>

    <!-- Manual Add Style Modal -->
    <div id="manualStyleModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 class="font-bold text-lg text-slate-900">Add Style Manually</h3>
            <div class="space-y-3 text-xs">
                <div>
                    <label class="block font-medium text-slate-700 mb-1">Style Name / Code</label>
                    <input type="text" id="manualStyleName" placeholder="e.g. 26S25BSS1LSZ7 - WS008" class="w-full border border-slate-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div>
                    <label class="block font-medium text-slate-700 mb-1">Costing ID / Revision (Optional)</label>
                    <input type="text" id="manualCostingId" placeholder="e.g. B-26-837" class="w-full border border-slate-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div>
                    <label class="block font-medium text-slate-700 mb-1">Garment Order Qty (Pcs)</label>
                    <input type="number" id="manualGarmentQty" placeholder="26500" class="w-full border border-slate-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
            </div>
            <div class="flex justify-end space-x-2 pt-2">
                <button onclick="closeManualStyleModal()" class="bg-slate-100 text-slate-700 text-xs font-semibold px-4 py-2 rounded-xl">Cancel</button>
                <button onclick="submitManualStyle()" class="bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-4 py-2 rounded-xl">Add Style</button>
            </div>
        </div>
    </div>

    <!-- Add Custom Task Modal -->
    <div id="addTaskModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 class="font-bold text-lg text-slate-900">Add Custom Task</h3>
            <p class="text-xs text-slate-500" id="addTaskStyleLabel"></p>
            <input type="hidden" id="addTaskStyleId">
            <div class="space-y-3 text-xs">
                <div>
                    <label class="block font-medium text-slate-700 mb-1">Item / Task Name</label>
                    <input type="text" id="taskNameInput" placeholder="e.g. Barcode Sticker / Wash Approval" class="w-full border border-slate-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div>
                    <label class="block font-medium text-slate-700 mb-1">Category</label>
                    <select id="taskCategorySelect" class="w-full border border-slate-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="Basic">Basic</option>
                        <option value="Fabric">Fabric</option>
                        <option value="Sewing Accs">Sewing Accs</option>
                        <option value="Finishing Accs">Finishing Accs</option>
                    </select>
                </div>
                <div>
                    <label class="block font-medium text-slate-700 mb-1">Initial Status / Update</label>
                    <input type="text" id="taskUpdateInput" placeholder="Pending booking / submission" class="w-full border border-slate-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
            </div>
            <div class="flex justify-end space-x-2 pt-2">
                <button onclick="closeAddTaskModal()" class="bg-slate-100 text-slate-700 text-xs font-semibold px-4 py-2 rounded-xl">Cancel</button>
                <button onclick="submitCustomTask()" class="bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-4 py-2 rounded-xl">Save Task</button>
            </div>
        </div>
    </div>

    <!-- Bulk Action for Selected Items Modal -->
    <div id="bulkActionModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-md w-full shadow-2xl border border-slate-100 overflow-hidden transform transition-all">
            <!-- Modal Header -->
            <div class="bg-gradient-to-r from-indigo-600 to-blue-600 px-6 py-4 text-white flex items-center justify-between">
                <div class="flex items-center space-x-2.5">
                    <div class="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center text-sm font-bold">
                        <i class="fa-solid fa-layer-group"></i>
                    </div>
                    <div>
                        <h3 class="font-bold text-sm">Action for Selected Items</h3>
                        <p class="text-[11px] text-indigo-100"><span id="bulkModalCount">0</span> items selected across styles</p>
                    </div>
                </div>
                <button onclick="closeBulkActionModal()" class="text-white/80 hover:text-white transition p-1">
                    <i class="fa-solid fa-xmark text-base"></i>
                </button>
            </div>

            <!-- Modal Form Body -->
            <div class="p-6 space-y-4">
                <div>
                    <label class="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                        1. Select Field to Update
                    </label>
                    <select id="bulkFieldSelect" onchange="onBulkFieldChanged(this.value)" class="w-full border border-slate-200 rounded-lg p-2.5 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-slate-50">
                        <option value="updates">Latest Status / Update Note</option>
                        <option value="task_notes">Task / Action Note</option>
                        <option value="color_approval">Color Approval</option>
                        <option value="status">Status</option>
                    </select>
                </div>

                <div>
                    <label class="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                        2. Desired Data / Value to Place
                    </label>
                    
                    <!-- Textarea for Updates & Task Notes -->
                    <div id="bulkValueTextWrapper">
                        <textarea id="bulkValueText" rows="3" placeholder="Enter note or status update (e.g. Approved, Closed, Booking in progress...)" class="w-full border border-slate-200 rounded-lg p-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"></textarea>
                        <p class="text-[10px] text-slate-400 mt-1">Tip: Setting note to 'Closed', 'Done', or 'Approved' automatically updates task Status as well.</p>
                    </div>

                    <!-- Dropdown for Status -->
                    <div id="bulkValueStatusWrapper" class="hidden">
                        <select id="bulkValueStatus" class="w-full border border-slate-200 rounded-lg p-2.5 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
                            <option value="Pending">Pending</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Approved">Approved</option>
                            <option value="Closed">Closed</option>
                            <option value="Done">Done</option>
                        </select>
                    </div>

                    <!-- Input & Quick buttons for Color Approval -->
                    <div id="bulkValueColorWrapper" class="hidden">
                        <input type="text" id="bulkValueColor" placeholder="e.g. Approved, Pending, Submitted" class="w-full border border-slate-200 rounded-lg p-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
                        <div class="flex flex-wrap gap-1 mt-2">
                            <button type="button" onclick="setBulkColorValue('Approved')" class="px-2 py-0.5 text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 rounded hover:bg-emerald-100 font-medium">Approved</button>
                            <button type="button" onclick="setBulkColorValue('Pending')" class="px-2 py-0.5 text-[10px] bg-slate-100 text-slate-700 border border-slate-200 rounded hover:bg-slate-200 font-medium">Pending</button>
                            <button type="button" onclick="setBulkColorValue('Submitted')" class="px-2 py-0.5 text-[10px] bg-blue-50 text-blue-700 border border-blue-200 rounded hover:bg-blue-100 font-medium">Submitted</button>
                            <button type="button" onclick="setBulkColorValue('Rejected')" class="px-2 py-0.5 text-[10px] bg-red-50 text-red-700 border border-red-200 rounded hover:bg-red-100 font-medium">Rejected</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Modal Footer -->
            <div class="bg-slate-50 px-6 py-3.5 border-t border-slate-100 flex items-center justify-end space-x-2">
                <button onclick="closeBulkActionModal()" class="px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-800 transition">
                    Cancel
                </button>
                <button onclick="submitBulkAction()" id="btnSubmitBulk" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg text-xs font-bold shadow-md transition flex items-center space-x-1.5">
                    <i class="fa-solid fa-check"></i>
                    <span>Submit & Update</span>
                </button>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast" class="fixed bottom-5 right-5 bg-slate-900 text-white text-xs font-medium px-4 py-3 rounded-xl shadow-lg border border-slate-700 transition transform translate-y-20 opacity-0 z-50"></div>

    <script>
        let currentCategoryFilter = 'all';
        let currentItemFilter = '';

        function showToast(msg, isError = false) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.className = isError 
                ? "fixed bottom-5 right-5 bg-red-600 text-white text-xs font-medium px-4 py-3 rounded-xl shadow-lg z-50 transition duration-300" 
                : "fixed bottom-5 right-5 bg-slate-900 text-white text-xs font-medium px-4 py-3 rounded-xl shadow-lg border border-slate-700 z-50 transition duration-300";
            t.style.transform = 'translateY(0)';
            t.style.opacity = '1';
            setTimeout(() => {
                t.style.transform = 'translateY(5rem)';
                t.style.opacity = '0';
            }, 3000);
        }

        function autoExpandTextarea(elem) {
            elem.style.height = 'auto';
            elem.style.height = (elem.scrollHeight) + 'px';
        }

        function syncStickyToolbarOffset() {
            const hdr = document.getElementById('topHeader');
            const bar = document.getElementById('stickyFilterToolbar');
            if (hdr && bar) {
                bar.style.top = hdr.offsetHeight + 'px';
            }
        }

        // Initialize all textareas and sticky bar offset on load
        window.addEventListener('DOMContentLoaded', () => {
            syncStickyToolbarOffset();
            document.querySelectorAll('textarea.auto-expand').forEach(ta => {
                autoExpandTextarea(ta);
            });
            applyFilters();
        });
        window.addEventListener('resize', syncStickyToolbarOffset);

        function toggleStyleAccordion(styleId) {
            const body = document.getElementById(`body_${styleId}`);
            const arrow = document.getElementById(`arrow_${styleId}`);
            if (!body) return;
            if (body.classList.contains('hidden')) {
                body.classList.remove('hidden');
                arrow.style.transform = 'rotate(0deg)';
                // Re-adjust textareas on expand
                body.querySelectorAll('textarea.auto-expand').forEach(ta => autoExpandTextarea(ta));
            } else {
                body.classList.add('hidden');
                arrow.style.transform = 'rotate(-90deg)';
            }
        }

        function expandAllStyles(expand) {
            const bodies = document.querySelectorAll('.accordion-body');
            const arrows = document.querySelectorAll('.accordion-arrow');
            bodies.forEach(b => {
                if (expand) {
                    b.classList.remove('hidden');
                    b.querySelectorAll('textarea.auto-expand').forEach(ta => autoExpandTextarea(ta));
                } else {
                    b.classList.add('hidden');
                }
            });
            arrows.forEach(a => {
                a.style.transform = expand ? 'rotate(0deg)' : 'rotate(-90deg)';
            });
        }

        function toggleCompletedFilter(hide) {
            applyFilters();
        }

        let selectedCategories = new Map(); // lower(category) -> display label
        let selectedStyles = new Map();     // styleId -> display label
        let selectedItems = new Map();      // lower(itemName) -> display label

        function getMultiState(kind) {
            const map = kind === 'category' ? selectedCategories : (kind === 'style' ? selectedStyles : selectedItems);
            return {
                map,
                panel: document.getElementById(kind + 'DropdownPanel'),
                input: document.getElementById(kind + 'SearchInput'),
                badge: document.getElementById(kind + 'FilterCount'),
                clearBtn: document.getElementById(kind + 'FilterClearBtn'),
                matchCount: document.getElementById(kind + 'MatchCount'),
                optSelector: '.multi-opt-' + kind,
                cbSelector: '.multi-cb-' + kind
            };
        }

        function openMultiDropdown(kind) {
            closeAllMultiDropdowns(kind);
            const st = getMultiState(kind);
            if (st.panel) st.panel.classList.remove('hidden');
            filterMultiOptions(kind, st.input ? st.input.value : '');
        }

        function toggleMultiDropdown(kind) {
            const st = getMultiState(kind);
            if (!st.panel) return;
            if (st.panel.classList.contains('hidden')) {
                openMultiDropdown(kind);
                if (st.input) st.input.focus();
            } else {
                st.panel.classList.add('hidden');
            }
        }

        function closeAllMultiDropdowns(exceptKind = null) {
            ['category', 'style', 'item'].forEach(k => {
                if (k !== exceptKind) {
                    const p = document.getElementById(k + 'DropdownPanel');
                    if (p) p.classList.add('hidden');
                }
            });
        }

        document.addEventListener('click', (e) => {
            ['category', 'style', 'item'].forEach(k => {
                const wrap = document.getElementById(k + 'FilterDropdownWrap');
                if (wrap && !wrap.contains(e.target)) {
                    document.getElementById(k + 'DropdownPanel')?.classList.add('hidden');
                }
            });
        });

        function filterMultiOptions(kind, query) {
            const st = getMultiState(kind);
            const q = (query || '').trim().toLowerCase();
            let visible = 0;
            document.querySelectorAll(st.optSelector).forEach(lbl => {
                const text = lbl.getAttribute('data-label') || '';
                if (!q || text.includes(q)) {
                    lbl.style.display = '';
                    visible++;
                } else {
                    lbl.style.display = 'none';
                }
            });
            if (st.matchCount) st.matchCount.innerText = visible;
        }

        function onMultiSearchInput(kind, val) {
            const st = getMultiState(kind);
            if (st.panel) st.panel.classList.remove('hidden');
            filterMultiOptions(kind, val);
            updateMultiFilterUI(kind);
            applyFilters();
        }

        function onMultiCheckboxChange(kind, cb) {
            const st = getMultiState(kind);
            const val = cb.value;
            const display = cb.getAttribute('data-display') || val;
            if (cb.checked) {
                st.map.set(val, display);
            } else {
                st.map.delete(val);
            }
            updateMultiFilterUI(kind);
            applyFilters();
        }

        function selectAllMatchingMulti(kind) {
            const st = getMultiState(kind);
            document.querySelectorAll(st.optSelector).forEach(lbl => {
                if (lbl.style.display !== 'none') {
                    const cb = lbl.querySelector(st.cbSelector);
                    if (cb) {
                        cb.checked = true;
                        st.map.set(cb.value, cb.getAttribute('data-display') || cb.value);
                    }
                }
            });
            updateMultiFilterUI(kind);
            applyFilters();
        }

        function clearMultiFilter(kind) {
            const st = getMultiState(kind);
            st.map.clear();
            if (st.input) st.input.value = '';
            document.querySelectorAll(st.cbSelector).forEach(cb => cb.checked = false);
            filterMultiOptions(kind, '');
            updateMultiFilterUI(kind);
            applyFilters();
        }

        function resetAllMultiFilters() {
            clearMultiFilter('category');
            clearMultiFilter('style');
            clearMultiFilter('item');
        }

        function updateMultiFilterUI(kind) {
            const st = getMultiState(kind);
            const count = st.map.size;
            const hasText = !!(st.input && st.input.value.trim() !== '');
            if (st.badge) {
                if (count > 0) {
                    st.badge.innerText = count;
                    st.badge.classList.remove('hidden');
                } else {
                    st.badge.classList.add('hidden');
                }
            }
            if (st.clearBtn) {
                if (count > 0 || hasText) st.clearBtn.classList.remove('hidden');
                else st.clearBtn.classList.add('hidden');
            }
            renderActiveFilterChips();
        }

        function renderActiveFilterChips() {
            const bar = document.getElementById('activeFilterChipsBar');
            const list = document.getElementById('activeFilterChipsList');
            if (!bar || !list) return;
            list.innerHTML = '';

            const addChip = (kind, key, label, colorClasses) => {
                const span = document.createElement('span');
                span.className = `inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${colorClasses}`;
                const txt = document.createElement('span');
                const prefix = kind === 'category' ? 'Category: ' : (kind === 'style' ? 'Style: ' : 'Item: ');
                txt.textContent = prefix + label;
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'hover:text-red-600 focus:outline-none ml-1';
                btn.innerHTML = '<i class="fa-solid fa-xmark text-[10px]"></i>';
                btn.addEventListener('click', () => {
                    const st = getMultiState(kind);
                    st.map.delete(key);
                    document.querySelectorAll(st.cbSelector).forEach(cb => {
                        if (cb.value === key) cb.checked = false;
                    });
                    updateMultiFilterUI(kind);
                    applyFilters();
                });
                span.appendChild(txt);
                span.appendChild(btn);
                list.appendChild(span);
            };

            selectedCategories.forEach((label, key) => addChip('category', key, label, 'bg-indigo-50 text-indigo-800 border-indigo-200'));
            selectedStyles.forEach((label, key) => addChip('style', key, label, 'bg-blue-50 text-blue-800 border-blue-200'));
            selectedItems.forEach((label, key) => addChip('item', key, label, 'bg-emerald-50 text-emerald-800 border-emerald-200'));

            if (selectedCategories.size > 0 || selectedStyles.size > 0 || selectedItems.size > 0) {
                bar.classList.remove('hidden');
            } else {
                bar.classList.add('hidden');
            }
        }

        function applyFilters() {
            const hideCompleted = document.getElementById('hideCompletedCheck').checked;
            const catQuery = (document.getElementById('categorySearchInput')?.value || '').trim().toLowerCase();
            const styleQuery = (document.getElementById('styleSearchInput')?.value || '').trim().toLowerCase();
            const itemQuery = (document.getElementById('itemSearchInput')?.value || '').trim().toLowerCase();

            const isFilteringCategory = (selectedCategories.size > 0 || catQuery !== '');
            const isFilteringStyle = (selectedStyles.size > 0 || styleQuery !== '');
            const isFilteringItem = (selectedItems.size > 0 || itemQuery !== '');

            const rows = document.querySelectorAll('.task-row');
            const visibleCountByStyle = {};

            rows.forEach(r => {
                const cat = (r.getAttribute('data-category') || '').toLowerCase();
                const itemName = (r.getAttribute('data-item-name') || '').toLowerCase();
                const isClosed = r.classList.contains('is-closed-task');

                let matchCat = true;
                if (selectedCategories.size > 0) {
                    matchCat = selectedCategories.has(cat);
                } else if (catQuery !== '') {
                    matchCat = cat.includes(catQuery);
                }

                let matchItem = true;
                if (selectedItems.size > 0) {
                    matchItem = selectedItems.has(itemName);
                } else if (itemQuery !== '') {
                    matchItem = itemName.includes(itemQuery);
                }

                let matchClosed = (!hideCompleted || !isClosed);
                // When filtering by specific item(s), never show already closed/completed rows for that item
                if (isFilteringItem && isClosed) {
                    matchClosed = false;
                }

                const styleId = r.getAttribute('data-style-id');

                if (matchCat && matchItem && matchClosed) {
                    r.style.display = '';
                    if (styleId) {
                        visibleCountByStyle[styleId] = (visibleCountByStyle[styleId] || 0) + 1;
                    }
                } else {
                    r.style.display = 'none';
                }
            });

            // Hide or show style cards based on Style Filter AND visible matching items
            document.querySelectorAll('.style-card').forEach(card => {
                const styleId = card.getAttribute('data-style-id') || card.id.replace('card_', '');
                const styleName = (card.getAttribute('data-style-name') || '').toLowerCase();

                let matchStyle = true;
                if (selectedStyles.size > 0) {
                    matchStyle = selectedStyles.has(styleId);
                } else if (styleQuery !== '') {
                    matchStyle = styleName.includes(styleQuery);
                }

                const count = visibleCountByStyle[styleId] || 0;
                const hasVisibleContent = (count > 0 || (!isFilteringItem && !isFilteringCategory && !hideCompleted));

                if (matchStyle && hasVisibleContent) {
                    card.style.display = '';
                    if (isFilteringItem || isFilteringStyle || isFilteringCategory) {
                        const body = document.getElementById(`body_${styleId}`);
                        const arrow = document.getElementById(`arrow_${styleId}`);
                        if (body) {
                            body.classList.remove('hidden');
                            body.querySelectorAll('textarea.auto-expand').forEach(ta => autoExpandTextarea(ta));
                        }
                        if (arrow) arrow.style.transform = 'rotate(0deg)';
                    }
                } else {
                    card.style.display = 'none';
                }
            });
        }

        function updateProgress(percent, message) {
            const sec = document.getElementById('progressSection');
            const bar = document.getElementById('progressBar');
            const pctLabel = document.getElementById('progressPercent');
            const msgLabel = document.getElementById('progressMessage');

            sec.classList.remove('hidden');
            bar.style.width = percent + '%';
            pctLabel.innerText = Math.round(percent) + '%';
            msgLabel.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i><span>${message}</span>`;

            if (percent >= 100) {
                setTimeout(() => {
                    msgLabel.innerHTML = `<i class="fa-solid fa-check text-emerald-500"></i><span>${message}</span>`;
                }, 300);
            }
        }

        const currentBuyerCode = "{{ current_buyer.code }}";
        let selectedTasks = new Set();

        function startSyncInhoused() {
            const btn = document.getElementById('btnSync');
            const icon = document.getElementById('syncIcon');
            btn.disabled = true;
            icon.classList.add('fa-spin');

            updateProgress(5, "Connecting to ERP for Inhoused updates...");

            const evtSource = new EventSource('/api/stream/sync-inhoused?buyer=' + encodeURIComponent(currentBuyerCode));
            evtSource.onmessage = function(e) {
                const data = JSON.parse(e.data);
                updateProgress(data.percent, data.message);

                if (data.done) {
                    evtSource.close();
                    btn.disabled = false;
                    icon.classList.remove('fa-spin');
                    showToast(data.message);
                    setTimeout(() => window.location.reload(), 1000);
                }
            };
            evtSource.onerror = function() {
                evtSource.close();
                btn.disabled = false;
                icon.classList.remove('fa-spin');
                showToast("Sync error", true);
            };
        }

        function startCheckAddNewStyles() {
            const btn = document.getElementById('btnAddStyles');
            const icon = document.getElementById('addIcon');
            btn.disabled = true;
            icon.classList.add('fa-spin');

            updateProgress(5, "Scanning ERP Running Styles & checking PO FFD dates...");

            const evtSource = new EventSource('/api/stream/check-add-new-styles?buyer=' + encodeURIComponent(currentBuyerCode));
            evtSource.onmessage = function(e) {
                const data = JSON.parse(e.data);
                updateProgress(data.percent, data.message);

                if (data.done) {
                    evtSource.close();
                    btn.disabled = false;
                    icon.classList.remove('fa-spin');
                    showToast(data.message);
                    setTimeout(() => window.location.reload(), 1200);
                }
            };
            evtSource.onerror = function() {
                evtSource.close();
                btn.disabled = false;
                icon.classList.remove('fa-spin');
                showToast("Style scan error", true);
            };
        }

        function changeBuyer(buyerCode) {
            showToast("Loading buyer data...");
            window.location.href = '/?buyer=' + encodeURIComponent(buyerCode);
        }

        async function saveField(styleId, taskId, field, value) {
            let autoStatus = null;
            if (field === 'updates') {
                const v = (value || '').toLowerCase();
                if (v.includes('closed')) autoStatus = 'Closed';
                else if (v.includes('done')) autoStatus = 'Done';
                else if (v.includes('approved')) autoStatus = 'Approved';
            }

            const row = document.getElementById(`row_${styleId}_${taskId}`);
            if (autoStatus && row) {
                const statusSelect = row.querySelector('select[data-field="status"]');
                if (statusSelect) {
                    statusSelect.value = autoStatus;
                    updateStatusStyle(statusSelect, autoStatus, row);
                }
            }

            const resp = await fetch('/api/update-task', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    style_id: styleId,
                    task_id: taskId,
                    field: field,
                    value: value
                })
            });

            if (resp.ok) {
                const data = await resp.json();
                if (data.updated && data.updated.status && row) {
                    const statusSelect = row.querySelector('select[data-field="status"]');
                    if (statusSelect) {
                        statusSelect.value = data.updated.status;
                        updateStatusStyle(statusSelect, data.updated.status, row);
                    }
                    if (document.getElementById('hideCompletedCheck')?.checked) {
                        applyFilters();
                    }
                }
            }
            showToast("Saved & Persisted");
        }

        function updateStatusStyle(selectEl, status, row) {
            selectEl.className = "text-[10px] font-semibold rounded px-1.5 py-0.5 border cursor-pointer focus:outline-none transition ";
            const s = (status || '').toLowerCase();
            if (s === 'closed' || s === 'done' || s === 'approved') {
                selectEl.className += "bg-emerald-100 text-emerald-800 border-emerald-300";
                if (row) row.classList.add('is-closed-task');
            } else if (s === 'in progress') {
                selectEl.className += "bg-amber-100 text-amber-800 border-amber-300";
                if (row) row.classList.remove('is-closed-task');
            } else {
                selectEl.className += "bg-slate-100 text-slate-700 border-slate-300";
                if (row) row.classList.remove('is-closed-task');
            }
        }

        function onTaskSelectChange(cb) {
            const key = cb.getAttribute('data-style-id') + ':::' + cb.getAttribute('data-task-id');
            if (cb.checked) {
                selectedTasks.add(key);
            } else {
                selectedTasks.delete(key);
            }
            updateSelectedCount();
        }

        function updateSelectedCount() {
            const count = selectedTasks.size;
            const btn = document.getElementById('bulkActionBtn');
            const badge = document.getElementById('selectedCountBadge');
            const btnClear = document.getElementById('btnClearSelections');
            
            if (count > 0) {
                btn.disabled = false;
                badge.innerText = count;
                badge.classList.remove('hidden');
                btnClear.classList.remove('hidden');
            } else {
                btn.disabled = true;
                badge.innerText = '0';
                badge.classList.add('hidden');
                btnClear.classList.add('hidden');
            }
            const modalCount = document.getElementById('bulkModalCount');
            if (modalCount) modalCount.innerText = count;
        }

        function toggleSelectStyleItems(styleId, checked) {
            const body = document.getElementById(`body_${styleId}`);
            if (!body) return;
            const cbs = body.querySelectorAll('.task-select-cb');
            cbs.forEach(cb => {
                const row = cb.closest('.task-row');
                if (row && row.style.display !== 'none') {
                    cb.checked = checked;
                    const key = cb.getAttribute('data-style-id') + ':::' + cb.getAttribute('data-task-id');
                    if (checked) selectedTasks.add(key);
                    else selectedTasks.delete(key);
                }
            });
            updateSelectedCount();
        }

        function isRowActuallyVisible(row) {
            if (!row || row.style.display === 'none') return false;
            const card = row.closest('.style-card');
            if (card && card.style.display === 'none') return false;
            return true;
        }

        function toggleSelectAllVisible() {
            const allRows = document.querySelectorAll('.task-row');
            let anyUnchecked = false;
            allRows.forEach(row => {
                if (isRowActuallyVisible(row)) {
                    const cb = row.querySelector('.task-select-cb');
                    if (cb && !cb.checked) anyUnchecked = true;
                }
            });

            const setChecked = anyUnchecked;
            allRows.forEach(row => {
                if (isRowActuallyVisible(row)) {
                    const cb = row.querySelector('.task-select-cb');
                    if (cb) {
                        cb.checked = setChecked;
                        const key = cb.getAttribute('data-style-id') + ':::' + cb.getAttribute('data-task-id');
                        if (setChecked) selectedTasks.add(key);
                        else selectedTasks.delete(key);
                    }
                }
            });
            document.querySelectorAll('.style-card').forEach(card => {
                if (card.style.display !== 'none') {
                    const sa = card.querySelector('.style-select-all');
                    if (sa) sa.checked = setChecked;
                }
            });
            updateSelectedCount();
            showToast(setChecked ? "Selected all visible items" : "Deselected all items");
        }

        function clearAllSelections() {
            selectedTasks.clear();
            document.querySelectorAll('.task-select-cb').forEach(cb => cb.checked = false);
            document.querySelectorAll('.style-select-all').forEach(sa => sa.checked = false);
            updateSelectedCount();
        }

        function openBulkActionModal() {
            if (selectedTasks.size === 0) return;
            document.getElementById('bulkModalCount').innerText = selectedTasks.size;
            document.getElementById('bulkActionModal').classList.remove('hidden');
            onBulkFieldChanged(document.getElementById('bulkFieldSelect').value);
        }

        function closeBulkActionModal() {
            document.getElementById('bulkActionModal').classList.add('hidden');
        }

        function onBulkFieldChanged(field) {
            const textWrap = document.getElementById('bulkValueTextWrapper');
            const statusWrap = document.getElementById('bulkValueStatusWrapper');
            const colorWrap = document.getElementById('bulkValueColorWrapper');

            textWrap.classList.add('hidden');
            statusWrap.classList.add('hidden');
            colorWrap.classList.add('hidden');

            if (field === 'status') {
                statusWrap.classList.remove('hidden');
            } else if (field === 'color_approval') {
                colorWrap.classList.remove('hidden');
            } else {
                textWrap.classList.remove('hidden');
                document.getElementById('bulkValueText').placeholder = field === 'updates' ? 
                    'Enter latest status / update note (e.g. Approved, Closed, Done, Booking in progress...)' : 
                    'Enter action note or remarks...';
            }
        }

        function setBulkColorValue(val) {
            document.getElementById('bulkValueColor').value = val;
        }

        async function submitBulkAction() {
            if (selectedTasks.size === 0) return;
            const field = document.getElementById('bulkFieldSelect').value;
            let value = '';

            if (field === 'status') {
                value = document.getElementById('bulkValueStatus').value;
            } else if (field === 'color_approval') {
                value = document.getElementById('bulkValueColor').value.trim() || 'Pending';
            } else {
                value = document.getElementById('bulkValueText').value.trim();
            }

            const items = [];
            selectedTasks.forEach(key => {
                const [styleId, taskId] = key.split(':::');
                items.push({style_id: styleId, task_id: taskId});
            });

            const btn = document.getElementById('btnSubmitBulk');
            btn.disabled = true;
            btn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i><span>Applying...</span>`;

            try {
                const resp = await fetch('/api/bulk-update-tasks', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        items: items,
                        field: field,
                        value: value
                    })
                });

                if (resp.ok) {
                    const data = await resp.json();
                    items.forEach(it => {
                        const row = document.getElementById(`row_${it.style_id}_${it.task_id}`);
                        if (row) {
                            if (field === 'updates') {
                                const ta = row.querySelector('textarea[data-field="updates"]');
                                if (ta) {
                                    ta.value = value;
                                    autoExpandTextarea(ta);
                                }
                                if (data.updated && data.updated.status) {
                                    const sel = row.querySelector('select[data-field="status"]');
                                    if (sel) {
                                        sel.value = data.updated.status;
                                        updateStatusStyle(sel, data.updated.status, row);
                                    }
                                }
                            } else if (field === 'task_notes') {
                                const ta = row.querySelector('textarea[data-field="task_notes"]');
                                if (ta) {
                                    ta.value = value;
                                    autoExpandTextarea(ta);
                                }
                            } else if (field === 'color_approval') {
                                const inp = row.querySelector('input[data-field="color_approval"]');
                                if (inp) inp.value = value;
                            } else if (field === 'status') {
                                const sel = row.querySelector('select[data-field="status"]');
                                if (sel) {
                                    sel.value = value;
                                    updateStatusStyle(sel, value, row);
                                }
                            }
                        }
                    });

                    closeBulkActionModal();
                    clearAllSelections();
                    showToast(`Updated ${data.count} items successfully!`);

                    if (document.getElementById('hideCompletedCheck')?.checked) {
                        applyFilters();
                    }
                } else {
                    showToast("Failed to apply bulk update", true);
                }
            } catch (e) {
                showToast("Error updating items: " + e.message, true);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-check"></i><span>Submit & Update</span>`;
            }
        }

        async function deleteTask(styleId, taskId) {
            if (!confirm("Are you sure you want to remove this task?")) return;
            const resp = await fetch('/api/delete-task', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({style_id: styleId, task_id: taskId})
            });
            if (resp.ok) {
                const row = document.getElementById(`row_${styleId}_${taskId}`);
                if (row) row.remove();
                showToast("Task removed");
            }
        }

        async function deleteStyle(styleId, styleName) {
            if (!confirm(`Are you sure you want to remove style ${styleName}?`)) return;
            const resp = await fetch('/api/delete-style', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({style_id: styleId})
            });
            if (resp.ok) {
                const card = document.getElementById(`card_${styleId}`);
                if (card) card.remove();
                showToast("Style removed");
            }
        }

        function openManualStyleModal() {
            document.getElementById('manualStyleModal').classList.remove('hidden');
        }
        function closeManualStyleModal() {
            document.getElementById('manualStyleModal').classList.add('hidden');
        }
        async function submitManualStyle() {
            const name = document.getElementById('manualStyleName').value.trim();
            const costing = document.getElementById('manualCostingId').value.trim();
            const qty = document.getElementById('manualGarmentQty').value.trim();
            if (!name) return alert("Style name required");

            const resp = await fetch('/api/add-manual-style', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name, costing_id: costing, garment_qty: qty})
            });
            if (resp.ok) {
                window.location.reload();
            }
        }

        function openAddTaskModal(styleId, styleName) {
            document.getElementById('addTaskStyleId').value = styleId;
            document.getElementById('addTaskStyleLabel').innerText = "Style: " + styleName;
            document.getElementById('taskNameInput').value = "";
            document.getElementById('taskUpdateInput').value = "";
            document.getElementById('addTaskModal').classList.remove('hidden');
        }
        function closeAddTaskModal() {
            document.getElementById('addTaskModal').classList.add('hidden');
        }
        async function submitCustomTask() {
            const styleId = document.getElementById('addTaskStyleId').value;
            const name = document.getElementById('taskNameInput').value.trim();
            const category = document.getElementById('taskCategorySelect').value;
            const update = document.getElementById('taskUpdateInput').value.trim();
            if (!name) return alert("Task name required");

            const resp = await fetch('/api/add-custom-task', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    style_id: styleId,
                    item_name: name,
                    category: category,
                    updates: update || 'Pending'
                })
            });
            if (resp.ok) {
                window.location.reload();
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    buyers = erp.get_buyers()
    buyer_code = request.args.get("buyer") or session.get("buyer_code") or "C/20/1"
    session["buyer_code"] = buyer_code

    if buyer_code == "ALL":
        current_buyer = {"code": "ALL", "name": "All Buyers"}
    else:
        current_buyer = next((b for b in buyers if b["code"] == buyer_code), {"code": "C/20/1", "name": "Kmart"})

    styles = storage.get_styles_by_buyer(current_buyer.get("code"))

    items_map = {}
    cats_seen = set()
    style_options = []
    total_styles = len(styles)
    pending_count = 0
    closed_count = 0

    for sid, s in styles.items():
        s_name = (s.get("style_name") or sid).strip()
        style_options.append({"id": sid, "name": s_name})
        s["tasks"] = sort_tasks(s.get("tasks", []))
        for t in s["tasks"]:
            cat_val = (t.get("category") or "").strip()
            if cat_val:
                cats_seen.add(cat_val)
            item_name = (t.get("item_name") or "").strip()
            if item_name:
                items_map.setdefault(item_name.lower(), item_name)
            if is_task_completed(t):
                closed_count += 1
            else:
                pending_count += 1

    base_cats = ["Basic", "Fabric", "Sewing Accs", "Finishing Accs"]
    extra_cats = sorted([c for c in cats_seen if c not in base_cats], key=lambda x: x.lower())
    category_options = base_cats + extra_cats
    unique_items = sorted(items_map.values(), key=lambda x: x.lower())
    style_options.sort(key=lambda x: x["name"].lower())

    return render_template_string(
        HTML_TEMPLATE,
        buyers=buyers,
        current_buyer=current_buyer,
        styles=styles,
        total_styles=total_styles,
        pending_count=pending_count,
        closed_count=closed_count,
        unique_items=unique_items,
        style_options=style_options,
        category_options=category_options
    )

@app.route("/api/set-buyer", methods=["POST"])
def set_buyer():
    data = request.json or {}
    code = data.get("code")
    session["buyer_code"] = code
    return jsonify({"success": True})

@app.route("/api/stream/check-add-new-styles")
def stream_check_add_new_styles():
    """Server-Sent Events (SSE) streaming progress while scanning ERP for running styles."""
    buyer_code = request.args.get("buyer") or session.get("buyer_code") or "C/20/1"
    buyers = erp.get_buyers()
    if buyer_code == "ALL":
        buyer = {"code": "C/20/1", "name": "Kmart"}
    else:
        buyer = next((b for b in buyers if b["code"] == buyer_code), {"code": "C/20/1", "name": "Kmart"})

    def generate():
        buyer_name = buyer.get("name", "")
        yield f"data: {json.dumps({'percent': 10, 'message': f'Fetching styles for {buyer_name}...', 'done': False})}\n\n"
        
        erp_styles = erp.get_styles_for_buyer(buyer["code"], running_only=True)
        existing_styles = storage.get_styles()
        
        total = len(erp_styles)
        if total == 0:
            yield f"data: {json.dumps({'percent': 100, 'message': f'No new running styles found for {buyer_name}.', 'done': True})}\n\n"
            return

        new_entries = []
        for idx, st in enumerate(erp_styles, 1):
            costing_id = st.get("costing_id")
            s_name = st.get("style_name")
            pct = 15 + int((idx / total) * 75)
            yield f"data: {json.dumps({'percent': pct, 'message': f'Checking [{idx}/{total}]: {s_name}...', 'done': False})}\n\n"

            if not costing_id or costing_id in existing_styles:
                continue

            try:
                ocb_details = erp.get_style_ocb_details(st["ocb_id"]) if st.get("ocb_id") else {}
                ocb_details = ocb_details or {}
                garment_qty = ocb_details.get("OrderQty") or 0
                fob = ocb_details.get("FOB") or ""

                costing_items = erp.get_costing_items(costing_id)
                bom_items = erp.get_bom_inhoused_status(costing_id)

                tasks = generate_style_tasks(costing_items, bom_items, garment_qty=garment_qty)

                new_entries.append((costing_id, {
                    "style_name": s_name,
                    "costing_id": costing_id,
                    "buyer_code": buyer["code"],
                    "buyer_name": buyer["name"],
                    "ocb_id": st.get("ocb_id"),
                    "garment_qty": garment_qty,
                    "garment_type": st.get("garment_type"),
                    "oc_date": st.get("oc_date"),
                    "first_ffd": st.get("first_ffd"),
                    "last_ffd": st.get("last_ffd"),
                    "first_tna_date": st.get("first_tna_date"),
                    "fob": fob,
                    "tasks": tasks
                }))
            except Exception as e:
                app.logger.warning(f"Error processing new style {s_name} ({costing_id}): {e}")

        if new_entries:
            yield f"data: {json.dumps({'percent': 95, 'message': f'Saving {len(new_entries)} new style(s) to database...', 'done': False})}\n\n"
            storage.upsert_styles_batch(new_entries)
        else:
            storage.set_last_synced()

        yield f"data: {json.dumps({'percent': 100, 'message': f'Completed! Added {len(new_entries)} running style(s) for {buyer_name}.', 'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/stream/sync-inhoused")
def stream_sync_inhoused():
    """Server-Sent Events (SSE) streaming progress while syncing Inhoused BOM quantities."""
    buyer_code = request.args.get("buyer") or session.get("buyer_code") or "C/20/1"

    def generate():
        styles = storage.get_styles_by_buyer(buyer_code)
        costing_ids = list(styles.keys())
        total = len(costing_ids)
        
        if total == 0:
            yield f"data: {json.dumps({'percent': 100, 'message': 'No styles in chart to sync.', 'done': True})}\n\n"
            return

        bom_results = {}
        for idx, cid in enumerate(costing_ids, 1):
            s_info = styles[cid]
            s_name = s_info.get("style_name") or cid
            pct = 5 + int((idx / total) * 85)
            yield f"data: {json.dumps({'percent': pct, 'message': f'Syncing [{idx}/{total}]: {s_name}...', 'done': False})}\n\n"

            try:
                bom_items = erp.get_bom_inhoused_status(cid)
                if bom_items:
                    bom_results[cid] = bom_items
            except Exception as e:
                app.logger.warning(f"Error syncing BOM for {cid} ({s_name}): {e}")

        yield f"data: {json.dumps({'percent': 95, 'message': 'Saving refreshed quantities to database...', 'done': False})}\n\n"
        updated_items = storage.apply_bom_updates_batch(bom_results, sort_tasks)
        yield f"data: {json.dumps({'percent': 100, 'message': f'Sync complete! Refreshed {updated_items} item quantities across {total} style(s).', 'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/update-task", methods=["POST"])
def update_task_field():
    data = request.json or {}
    style_id = data.get("style_id")
    task_id = data.get("task_id")
    field = data.get("field")
    value = data.get("value")

    if style_id and task_id and field:
        update_dict = {field: value}
        if field == "updates":
            val_lower = str(value).strip().lower()
            if "closed" in val_lower:
                update_dict["status"] = "Closed"
            elif "done" in val_lower:
                update_dict["status"] = "Done"
            elif "approved" in val_lower:
                update_dict["status"] = "Approved"

        storage.update_task(style_id, task_id, update_dict)
        return jsonify({"success": True, "updated": update_dict})
    return jsonify({"success": False}), 400

@app.route("/api/bulk-update-tasks", methods=["POST"])
def bulk_update_tasks_route():
    data = request.json or {}
    items = data.get("items", [])
    field = data.get("field")
    value = data.get("value")

    if not items or not field:
        return jsonify({"success": False, "message": "Missing items or field"}), 400

    update_dict = {field: value}
    if field == "updates":
        val_lower = str(value).strip().lower()
        if "closed" in val_lower:
            update_dict["status"] = "Closed"
        elif "done" in val_lower:
            update_dict["status"] = "Done"
        elif "approved" in val_lower:
            update_dict["status"] = "Approved"

    count = storage.bulk_update_tasks(items, update_dict)
    return jsonify({"success": True, "count": count, "updated": update_dict})

@app.route("/api/add-manual-style", methods=["POST"])
def add_manual_style():
    data = request.json or {}
    name = data.get("name")
    costing_id = data.get("costing_id") or f"MANUAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    garment_qty = data.get("garment_qty") or 0

    costing_items = erp.get_costing_items(costing_id) if "B-" in costing_id else []
    bom_items = erp.get_bom_inhoused_status(costing_id) if "B-" in costing_id else []
    tasks = generate_style_tasks(costing_items, bom_items, garment_qty=garment_qty)

    buyer_code = session.get("buyer_code") or "C/20/1"
    buyers = erp.get_buyers()
    current_buyer = next((b for b in buyers if b["code"] == buyer_code), {"code": "C/20/1", "name": "Kmart"})

    storage.upsert_style(costing_id, {
        "style_name": name,
        "costing_id": costing_id,
        "buyer_code": current_buyer.get("code"),
        "buyer_name": current_buyer.get("name"),
        "garment_qty": garment_qty,
        "garment_type": "Manual",
        "oc_date": "N/A",
        "first_ffd": "N/A",
        "last_ffd": "N/A",
        "first_tna_date": "N/A",
        "tasks": tasks
    })
    return jsonify({"success": True})

@app.route("/api/delete-style", methods=["POST"])
def delete_style():
    data = request.json or {}
    style_id = data.get("style_id")
    if style_id:
        storage.delete_style(style_id)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/add-custom-task", methods=["POST"])
def add_custom_task():
    data = request.json or {}
    style_id = data.get("style_id")
    if style_id:
        storage.add_custom_task(style_id, {
            "item_name": data.get("item_name"),
            "category": data.get("category", "Basic"),
            "updates": data.get("updates", "Pending"),
            "task_notes": "",
            "booked_qty": 0,
            "ih_qty": 0,
            "bal_qty": 0,
            "color_approval": "Pending",
            "status": "Pending"
        })
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/delete-task", methods=["POST"])
def delete_task():
    data = request.json or {}
    style_id = data.get("style_id")
    task_id = data.get("task_id")
    if style_id and task_id:
        storage.delete_task(style_id, task_id)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/export/excel")
def export_excel():
    buyer_code = request.args.get("buyer") or session.get("buyer_code") or "C/20/1"
    buyers = erp.get_buyers()
    if buyer_code == "ALL":
        current_buyer = {"code": "ALL", "name": "All Buyers"}
    else:
        current_buyer = next((b for b in buyers if b["code"] == buyer_code), {"code": "C/20/1", "name": "Kmart"})

    styles = storage.get_styles_by_buyer(current_buyer.get("code"))
    data_to_export = {
        "selected_buyer": current_buyer,
        "styles": styles
    }
    output_path = BASE_DIR / f"AGDL_TNA_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    generate_excel_report(data_to_export, output_path)
    return send_file(output_path, as_attachment=True, download_name=output_path.name)

@app.route("/export/pdf")
def export_pdf():
    buyer_code = request.args.get("buyer") or session.get("buyer_code") or "C/20/1"
    buyers = erp.get_buyers()
    if buyer_code == "ALL":
        current_buyer = {"code": "ALL", "name": "All Buyers"}
    else:
        current_buyer = next((b for b in buyers if b["code"] == buyer_code), {"code": "C/20/1", "name": "Kmart"})

    styles = storage.get_styles_by_buyer(current_buyer.get("code"))
    data_to_export = {
        "selected_buyer": current_buyer,
        "styles": styles
    }
    output_path = BASE_DIR / f"AGDL_TNA_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    generate_pdf_report(data_to_export, output_path)
    return send_file(output_path, as_attachment=True, download_name=output_path.name)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting AGDL T&A Tracker Web Server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
