// bindings/py_exchange.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/bytes.h>
#include "matching_engine.hpp"
#include "binary_protocol.hpp"
#include "multi_asset_engine.hpp"

namespace py = pybind11;
using namespace exsim;

PYBIND11_MODULE(exchange_simulator, m) {
    m.doc() = "Python bindings for the C++ AstraX engine";

    // Enums
    py::enum_<Side>(m, "Side")
        .value("Buy", Side::Buy)
        .value("Sell", Side::Sell);

    py::enum_<OrderType>(m, "OrderType")
        .value("Limit", OrderType::Limit)
        .value("Market", OrderType::Market)
        .value("Stop", OrderType::Stop)
        .value("StopLimit", OrderType::StopLimit)
        .value("Pegged", OrderType::Pegged);

    py::enum_<TimeInForce>(m, "TimeInForce")
        .value("GTC", TimeInForce::GTC)
        .value("IOC", TimeInForce::IOC)
        .value("FOK", TimeInForce::FOK);

    py::enum_<Phase>(m, "Phase")
        .value("PreOpen", Phase::PreOpen)
        .value("Continuous", Phase::Continuous);

    py::enum_<CancelResult>(m, "CancelResult")
        .value("Success", CancelResult::Success)
        .value("OrderNotFound", CancelResult::OrderNotFound)
        .value("AlreadyFilled", CancelResult::AlreadyFilled);

    // Order struct
    py::class_<Order>(m, "Order")
        .def(py::init<>())
        .def_readwrite("id", &Order::id)
        .def_readwrite("price", &Order::price)
        .def_readwrite("stop_price", &Order::stop_price)
        .def_readwrite("peg_offset", &Order::peg_offset)
        .def_readwrite("quantity", &Order::quantity)
        .def_readwrite("filled_quantity", &Order::filled_quantity)
        .def_readwrite("visible_quantity", &Order::visible_quantity)
        .def_readwrite("hidden_quantity", &Order::hidden_quantity)
        .def_readwrite("side", &Order::side)
        .def_readwrite("type", &Order::type)
        .def_readwrite("tif", &Order::tif)
        .def_readwrite("timestamp", &Order::timestamp)
        .def("remaining", &Order::remaining)
        .def("is_filled", &Order::is_filled)
        .def("is_iceberg", &Order::is_iceberg);

    // Fill struct
    py::class_<Fill>(m, "Fill")
        .def_readonly("maker_order_id", &Fill::maker_order_id)
        .def_readonly("taker_order_id", &Fill::taker_order_id)
        .def_readonly("price", &Fill::price)
        .def_readonly("quantity", &Fill::quantity)
        .def_readonly("aggressor_side", &Fill::aggressor_side)
        .def_readonly("timestamp", &Fill::timestamp);

    py::class_<MultiAssetEngine::SymbolOrder>(m, "SymbolOrder")
        .def(py::init<>())
        .def_readwrite("symbol_id", &MultiAssetEngine::SymbolOrder::symbol_id)
        .def_readwrite("order", &MultiAssetEngine::SymbolOrder::order);

    py::class_<MultiAssetEngine::SymbolBatchResult>(m, "SymbolBatchResult")
        .def(py::init<>())
        .def_readwrite("symbol_id", &MultiAssetEngine::SymbolBatchResult::symbol_id)
        .def_readwrite("fills", &MultiAssetEngine::SymbolBatchResult::fills);

    py::class_<BinaryProtocol>(m, "BinaryProtocol")
        .def_static("order_size", &BinaryProtocol::order_size)
        .def_static("fill_size", &BinaryProtocol::fill_size)
        .def_static("encode_order", [](const Order& order) {
            auto bytes = BinaryProtocol::encode_order(order);
            return py::bytes(reinterpret_cast<const char*>(bytes.data()), bytes.size());
        })
        .def_static("decode_order", [](py::bytes data) {
            std::string buffer = data;
            std::vector<std::uint8_t> bytes(buffer.begin(), buffer.end());
            auto order = BinaryProtocol::decode_order(bytes);
            if (!order) return py::none();
            return py::cast(*order);
        })
        .def_static("encode_fill", [](const Fill& fill) {
            auto bytes = BinaryProtocol::encode_fill(fill);
            return py::bytes(reinterpret_cast<const char*>(bytes.data()), bytes.size());
        })
        .def_static("decode_fill", [](py::bytes data) {
            std::string buffer = data;
            std::vector<std::uint8_t> bytes(buffer.begin(), buffer.end());
            auto fill = BinaryProtocol::decode_fill(bytes);
            if (!fill) return py::none();
            return py::cast(*fill);
        });

    // OrderBook (read-only access via MatchingEngine::book())
    py::class_<OrderBook>(m, "OrderBook")
        .def("bid_depth", &OrderBook::bid_depth)
        .def("ask_depth", &OrderBook::ask_depth)
        .def("spread", &OrderBook::spread)
        .def("best_bid_price", [](const OrderBook& book) -> py::object {
            auto* level = book.best_bid();
            if (!level) return py::none();
            return py::cast(level->price);
        })
        .def("best_ask_price", [](const OrderBook& book) -> py::object {
            auto* level = book.best_ask();
            if (!level) return py::none();
            return py::cast(level->price);
        })
        .def("bid_levels", [](const OrderBook& book, size_t limit) {
            std::vector<std::pair<Price, Quantity>> out;
            for (auto it = book.bids_begin(); it != book.bids_end() && out.size() < limit; ++it)
                out.emplace_back(it->first, it->second.total_quantity);
            return out;
        }, py::arg("limit") = 10)
        .def("ask_levels", [](const OrderBook& book, size_t limit) {
            std::vector<std::pair<Price, Quantity>> out;
            for (auto it = book.asks_begin(); it != book.asks_end() && out.size() < limit; ++it)
                out.emplace_back(it->first, it->second.total_quantity);
            return out;
        }, py::arg("limit") = 10);

    // MatchingEngine
    py::class_<MatchingEngine>(m, "MatchingEngine")
        .def(py::init<>())
        .def("submit", &MatchingEngine::submit)
        .def("cancel", &MatchingEngine::cancel)
        .def("uncross", &MatchingEngine::uncross)
        .def("set_phase", &MatchingEngine::set_phase)
        .def("phase", &MatchingEngine::phase)
        .def("book", &MatchingEngine::book, py::return_value_policy::reference_internal)
        .def("stop_order_count", &MatchingEngine::stop_order_count)
        .def("pegged_order_count", &MatchingEngine::pegged_order_count);

    // MultiAssetEngine
    py::class_<MultiAssetEngine>(m, "MultiAssetEngine")
        .def(py::init<>())
        .def("get_book", &MultiAssetEngine::get_book, py::return_value_policy::reference_internal)
        .def("submit", &MultiAssetEngine::submit, py::arg("symbol_id"), py::arg("order"))
        .def("submit_parallel", &MultiAssetEngine::submit_parallel)
        .def("cancel", &MultiAssetEngine::cancel, py::arg("order_id"))
        .def("symbols", &MultiAssetEngine::symbols);
}

// AstraX repo sync
