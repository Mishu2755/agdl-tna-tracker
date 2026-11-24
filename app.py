import os
import io
import json
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file, redirect, url_for, Response

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
    <header class="bg-slate-900 text-white shadow-md sticky top-0 z-50 w-full">
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
                <a href="/export/excel" class="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center space-x-1.5 shadow transition">
                    <i class="fa-solid fa-file-excel text-sm"></i>
                    <span>Export Excel</span>
                </a>

                <!-- Export PDF (A4 Full Width) -->
                <a href="/export/pdf" target="_blank" class="bg-red-600 hover:bg-red-500 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center space-x-1.5 shadow transition">
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

        <!-- Mode Toggle & Filter Bar: Style-Wise vs Item/Category Batch Update -->
        <div class="bg-white p-3 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-3 w-full">
            <div class="flex flex-wrap items-center gap-1.5">
                <span class="text-xs font-bold text-slate-700 uppercase tracking-wide mr-1">
                    <i class="fa-solid fa-sliders text-blue-600 mr-1"></i> Update Mode:
                </span>
                <button onclick="setFilterMode('all')" id="btnFilterAll" class="filter-tab px-3 py-1 rounded-lg text-xs font-semibold bg-blue-600 text-white shadow-sm transition">
                    All Categories
                </button>
                <button onclick="setFilterMode('Basic')" id="btnFilterBasic" class="filter-tab px-3 py-1 rounded-lg text-xs font-semibold bg-slate-50 text-slate-700 hover:bg-slate-200 border border-slate-200 transition">
                    Basic Milestones
                </button>
                <button onclick="setFilterMode('Fabric')" id="btnFilterFabric" class="filter-tab px-3 py-1 rounded-lg text-xs font-semibold bg-slate-50 text-slate-700 hover:bg-slate-200 border border-slate-200 transition">
                    Fabric Items
                </button>
                <button onclick="setFilterMode('Sewing Accs')" id="btnFilterSewing" class="filter-tab px-3 py-1 rounded-lg text-xs font-semibold bg-slate-50 text-slate-700 hover:bg-slate-200 border border-slate-200 transition">
                    Sewing Accs
                </button>
                <button onclick="setFilterMode('Finishing Accs')" id="btnFilterFinishing" class="filter-tab px-3 py-1 rounded-lg text-xs font-semibold bg-slate-50 text-slate-700 hover:bg-slate-200 border border-slate-200 transition">
                    Finishing Accs
                </button>
            </div>

            <!-- Specific Item Quick Filter (Fabric, Sewing Thread, Poly, Carton, etc.) -->
            <div class="flex items-center space-x-2">
                <span class="text-xs font-medium text-slate-500">Quick Item Filter:</span>
                <select id="itemQuickFilter" onchange="filterSpecificItem(this.value)" class="text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer">
                    <option value="">-- Show All Items --</option>
                    {% for item in unique_items %}
                    <option value="{{ item }}">{{ item }}</option>
                    {% endfor %}
                </select>
                <button onclick="expandAllStyles(true)" class="text-xs text-blue-600 hover:underline px-2 py-0.5 font-medium">Expand All</button>
                <span class="text-slate-300">|</span>
                <button onclick="expandAllStyles(false)" class="text-xs text-slate-500 hover:underline px-2 py-0.5 font-medium">Collapse All</button>
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
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden transition-all duration-200 style-card w-full" id="card_{{ style_id }}">
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
                                <th class="py-2.5 px-3 w-[100px]">Category</th>
                                <th class="py-2.5 px-3 w-[160px]">Item / Event</th>
                                <th class="py-2.5 px-3 w-[34%]">Latest Status / Update Note</th>
                                <th class="py-2.5 px-3 w-[26%]">Task / Action Note</th>
                                <th class="py-2.5 px-2 w-[75px] text-right">Book Qty</th>
                                <th class="py-2.5 px-2 w-[75px] text-right">I/H Qty</th>
                                <th class="py-2.5 px-2 w-[75px] text-right">Bal Qty</th>
                                <th class="py-2.5 px-2 w-[100px] text-center">Color Approval</th>
                                <th class="py-2.5 px-2 w-[85px] text-center">Status</th>
                                <th class="py-2.5 px-1 w-[40px] text-center">Del</th>
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
                                data-category="{{ t.category }}" 
                                data-item-name="{{ t.item_name|lower }}">
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
                                    <textarea oninput="autoExpandTextarea(this)" 
                                        onblur="saveField('{{ style_id }}', '{{ t.id }}', 'updates', this.value)" 
                                        class="auto-expand w-full bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-blue-500 p-1.5 rounded text-xs transition focus:outline-none text-slate-700" 
                                        rows="1">{{ t.updates }}</textarea>
                                </td>
                                <td class="py-2 px-3 align-top">
                                    <textarea oninput="autoExpandTextarea(this)" 
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
                                    <input type="text" value="{{ t.color_approval or 'Pending' }}" 
                                        onblur="saveField('{{ style_id }}', '{{ t.id }}', 'color_approval', this.value)" 
                                        class="w-full text-center bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-blue-500 px-1 py-0.5 rounded text-[11px] font-medium text-slate-700 focus:outline-none">
                                </td>
                                <td class="py-2 px-2 align-top text-center">
                                    <select onchange="saveField('{{ style_id }}', '{{ t.id }}', 'status', this.value)" 
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

        // Initialize all textareas on load
        window.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('textarea.auto-expand').forEach(ta => {
                autoExpandTextarea(ta);
            });
            applyFilters();
        });

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

        function setFilterMode(cat) {
            currentCategoryFilter = cat;
            document.querySelectorAll('.filter-tab').forEach(btn => {
                btn.className = "filter-tab px-3 py-1 rounded-lg text-xs font-semibold bg-slate-50 text-slate-700 hover:bg-slate-200 border border-slate-200 transition";
            });
            const activeId = cat === 'all' ? 'btnFilterAll' : (cat === 'Basic' ? 'btnFilterBasic' : (cat === 'Fabric' ? 'btnFilterFabric' : (cat === 'Sewing Accs' ? 'btnFilterSewing' : 'btnFilterFinishing')));
            const activeBtn = document.getElementById(activeId);
            if (activeBtn) activeBtn.className = "filter-tab px-3 py-1 rounded-lg text-xs font-semibold bg-blue-600 text-white shadow-sm transition";
            applyFilters();
        }

        function filterSpecificItem(val) {
            currentItemFilter = val.trim().toLowerCase();
            applyFilters();
        }

        function applyFilters() {
            const hideCompleted = document.getElementById('hideCompletedCheck').checked;
            const rows = document.querySelectorAll('.task-row');

            // Track which style cards have at least one visible row
            const visibleCountByStyle = {};

            rows.forEach(r => {
                const cat = r.getAttribute('data-category');
                const itemName = r.getAttribute('data-item-name');
                const isClosed = r.classList.contains('is-closed-task');

                let matchCat = (currentCategoryFilter === 'all' || cat === currentCategoryFilter);
                let matchItem = (!currentItemFilter || itemName.includes(currentItemFilter));
                let matchClosed = (!hideCompleted || !isClosed);

                // When filtering by a specific item, never show already closed/completed rows for that item
                if (currentItemFilter && isClosed) {
                    matchClosed = false;
                }

                // Get style card id from row id: row_<styleId>_<taskId>
                const rowId = r.id || "";
                const parts = rowId.split("_");
                const styleId = parts.length >= 2 ? parts[1] : null;

                if (matchCat && matchItem && matchClosed) {
                    r.style.display = '';
                    if (styleId) {
                        visibleCountByStyle[styleId] = (visibleCountByStyle[styleId] || 0) + 1;
                    }
                } else {
                    r.style.display = 'none';
                }
            });

            // Hide or show style cards based on whether they have visible matching items
            document.querySelectorAll('.style-card').forEach(card => {
                const cardId = card.id || "";
                const styleId = cardId.replace("card_", "");
                const count = visibleCountByStyle[styleId] || 0;

                if (count > 0 || (!currentItemFilter && currentCategoryFilter === 'all' && !hideCompleted)) {
                    card.style.display = '';
                    // If filtering by specific item, auto-expand the card so user sees it right away
                    if (currentItemFilter) {
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

        function startSyncInhoused() {
            const btn = document.getElementById('btnSync');
            const icon = document.getElementById('syncIcon');
            btn.disabled = true;
            icon.classList.add('fa-spin');

            updateProgress(5, "Connecting to ERP for Inhoused updates...");

            const evtSource = new EventSource('/api/stream/sync-inhoused');
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

            const evtSource = new EventSource('/api/stream/check-add-new-styles');
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

        async function changeBuyer(buyerCode) {
            showToast("Switching buyer...");
            const resp = await fetch('/api/set-buyer', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({code: buyerCode})
            });
            if (resp.ok) {
                window.location.reload();
            }
        }

        async function saveField(styleId, taskId, field, value) {
            await fetch('/api/update-task', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    style_id: styleId,
                    task_id: taskId,
                    field: field,
                    value: value
                })
            });
            showToast("Saved & Persisted");
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
    current_buyer = storage.get_buyer()
    styles = storage.get_styles_by_buyer(current_buyer.get("code"))

    items_set = set()
    total_styles = len(styles)
    pending_count = 0
    closed_count = 0

    for s in styles.values():
        for t in s.get("tasks", []):
            item_name = t.get("item_name")
            if item_name:
                items_set.add(item_name)
            if is_task_completed(t):
                closed_count += 1
            else:
                pending_count += 1

    unique_items = sorted(list(items_set))

    return render_template_string(
        HTML_TEMPLATE,
        buyers=buyers,
        current_buyer=current_buyer,
        styles=styles,
        total_styles=total_styles,
        pending_count=pending_count,
        closed_count=closed_count,
        unique_items=unique_items
    )

@app.route("/api/set-buyer", methods=["POST"])
def set_buyer():
    data = request.json or {}
    code = data.get("code")
    if code == "ALL":
        storage.set_buyer("ALL", "All Buyers")
        return jsonify({"success": True})
    buyers = erp.get_buyers()
    matched = next((b for b in buyers if b["code"] == code), None)
    if matched:
        storage.set_buyer(matched["code"], matched["name"])
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Buyer not found"}), 404

@app.route("/api/stream/check-add-new-styles")
def stream_check_add_new_styles():
    """Server-Sent Events (SSE) streaming progress while scanning ERP for running styles."""
    def generate():
        buyer = storage.get_buyer()
        buyer_name = buyer.get("name", "")
        yield f"data: {json.dumps({'percent': 10, 'message': f'Fetching styles for {buyer_name}...', 'done': False})}\n\n"
        
        erp_styles = erp.get_styles_for_buyer(buyer["code"], running_only=True)
        existing_styles = storage.get_styles()
        
        total = len(erp_styles)
        if total == 0:
            yield f"data: {json.dumps({'percent': 100, 'message': f'No new running styles found for {buyer_name}.', 'done': True})}\n\n"
            return

        added_count = 0
        for idx, st in enumerate(erp_styles, 1):
            costing_id = st.get("costing_id")
            s_name = st.get("style_name")
            pct = 15 + int((idx / total) * 80)
            yield f"data: {json.dumps({'percent': pct, 'message': f'Processing [{idx}/{total}]: {s_name}...', 'done': False})}\n\n"

            if not costing_id or costing_id in existing_styles:
                continue

            ocb_details = erp.get_style_ocb_details(st["ocb_id"]) if st.get("ocb_id") else {}
            garment_qty = ocb_details.get("OrderQty") or 0
            fob = ocb_details.get("FOB") or ""

            costing_items = erp.get_costing_items(costing_id)
            bom_items = erp.get_bom_inhoused_status(costing_id)

            tasks = generate_style_tasks(costing_items, bom_items, garment_qty=garment_qty)

            storage.upsert_style(costing_id, {
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
            })
            added_count += 1

        storage.set_last_synced()
        yield f"data: {json.dumps({'percent': 100, 'message': f'Completed! Added {added_count} running style(s).', 'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/stream/sync-inhoused")
def stream_sync_inhoused():
    """Server-Sent Events (SSE) streaming progress while syncing Inhoused BOM quantities."""
    def generate():
        buyer = storage.get_buyer()
        styles = storage.get_styles_by_buyer(buyer.get("code"))
        costing_ids = list(styles.keys())
        total = len(costing_ids)
        
        if total == 0:
            yield f"data: {json.dumps({'percent': 100, 'message': 'No styles in chart to sync.', 'done': True})}\n\n"
            return

        updated_items = 0
        for idx, cid in enumerate(costing_ids, 1):
            s_info = styles[cid]
            s_name = s_info.get("style_name") or cid
            pct = int((idx / total) * 95)
            yield f"data: {json.dumps({'percent': pct, 'message': f'Syncing [{idx}/{total}]: {s_name}...', 'done': False})}\n\n"

            bom_items = erp.get_bom_inhoused_status(cid)
            if not bom_items:
                continue

            bom_map = {b["item_name"].lower(): b for b in bom_items}
            tasks = s_info.get("tasks", [])

            for t in tasks:
                if not t.get("is_costing"):
                    continue
                t_name = t.get("item_name", "").lower()
                matched = bom_map.get(t_name)
                if not matched:
                    for b_name, b_val in bom_map.items():
                        if b_name in t_name or t_name in b_name:
                            matched = b_val
                            break

                if matched:
                    t["booked_qty"] = matched["booked_qty"]
                    t["ih_qty"] = matched["ih_qty"]
                    t["bal_qty"] = matched["bal_qty"]
                    t["uom"] = matched["uom"] or t.get("uom")

                    if matched["booked_qty"] > 0 and matched["bal_qty"] <= 0 and matched["ih_qty"] > 0:
                        t["status"] = "Closed"
                        t["updates"] = f"Fully Inhoused ({matched['ih_qty']:g} {t['uom']})"
                    elif matched["ih_qty"] > 0:
                        t["updates"] = f"{matched['booked_qty']:g} {t['uom']} Booked, {matched['ih_qty']:g} {t['uom']} Inhoused, Balance to i/h {matched['bal_qty']:g} {t['uom']}"
                    updated_items += 1

            s_info["tasks"] = sort_tasks(tasks)
            storage.upsert_style(cid, s_info)

        storage.set_last_synced()
        yield f"data: {json.dumps({'percent': 100, 'message': f'Sync complete! Refreshed {updated_items} item quantities.', 'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/update-task", methods=["POST"])
def update_task_field():
    data = request.json or {}
    style_id = data.get("style_id")
    task_id = data.get("task_id")
    field = data.get("field")
    value = data.get("value")

    if style_id and task_id and field:
        storage.update_task(style_id, task_id, {field: value})
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/add-manual-style", methods=["POST"])
def add_manual_style():
    data = request.json or {}
    name = data.get("name")
    costing_id = data.get("costing_id") or f"MANUAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    garment_qty = data.get("garment_qty") or 0

    costing_items = erp.get_costing_items(costing_id) if "B-" in costing_id else []
    bom_items = erp.get_bom_inhoused_status(costing_id) if "B-" in costing_id else []
    tasks = generate_style_tasks(costing_items, bom_items, garment_qty=garment_qty)

    current_buyer = storage.get_buyer()
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
    current_buyer = storage.get_buyer()
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
    current_buyer = storage.get_buyer()
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
